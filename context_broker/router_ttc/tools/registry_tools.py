"""Tool registry and lightweight retrieval for the Universal Context Router."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from contextlib import closing
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from context_broker.client_ttc.tools.contract_tools import DownstreamCapabilities
from context_broker.config import CACHE_DIR
from context_broker.storage_ttc.tools.json_tools import atomic_write_json
from context_broker.utils import log

_WORD_RE = re.compile(r"[a-zA-Z0-9_\-/]+")


@dataclass(frozen=True)
class ToolDescriptor:
    """Serializable description of one client-agnostic MCP tool.

    The original token-slim router fields are preserved. UCR fields have safe
    defaults so existing descriptor constructors and cache files remain valid.
    """

    id: str
    name: str
    category: str = "general"
    description: str = ""
    schema_summary: str = "{}"
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    risk_level: str = "low"
    file_capable: bool = False
    network_capable: bool = False
    shell_capable: bool = False
    server: str = "context-broker"
    embedding: list[float] = field(default_factory=list)
    latency_ms: float | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolDescriptor":
        """Build a descriptor from a JSON payload."""
        capabilities = dict(payload.get("capabilities", {}))
        file_capable = bool(payload.get("file_capable", capabilities.get("file", False)))
        network_capable = bool(payload.get("network_capable", capabilities.get("network", False)))
        shell_capable = bool(payload.get("shell_capable", capabilities.get("shell", False)))
        if not capabilities:
            capabilities = {
                "file": file_capable,
                "network": network_capable,
                "shell": shell_capable,
            }
        return cls(
            id=str(payload["id"]),
            name=str(payload.get("name", payload["id"])),
            category=str(payload.get("category", "general")),
            description=str(payload.get("description", "")),
            schema_summary=str(payload.get("schema_summary", "{}")),
            tags=list(payload.get("tags", [])),
            permissions=list(payload.get("permissions", [])),
            risk_level=str(payload.get("risk_level", payload.get("risk", "low"))),
            file_capable=file_capable,
            network_capable=network_capable,
            shell_capable=shell_capable,
            server=str(payload.get("server", "context-broker")),
            embedding=[float(value) for value in payload.get("embedding", [])],
            latency_ms=(
                float(payload["latency_ms"])
                if payload.get("latency_ms") is not None
                else None
            ),
            capabilities=capabilities,
        )

    @classmethod
    def from_downstream_tool(cls, server: str, tool_payload: dict[str, Any]) -> "ToolDescriptor":
        """Create a registry descriptor from a downstream MCP tool descriptor."""
        name = str(tool_payload.get("name", ""))
        schema = tool_payload.get("input_schema", {})
        return cls(
            id=f"{server}.{name}",
            name=name,
            server=server,
            category="downstream",
            description=str(tool_payload.get("description", "")),
            schema_summary=json.dumps(schema, sort_keys=True) if schema else "{}",
            tags=[server, "downstream", "mcp", name.replace("_", "-")],
            permissions=["downstream_mcp_call"],
            risk_level="medium",
            network_capable=True,
            capabilities={"file": False, "network": True, "shell": False, "downstream": True},
        )

    def searchable_text(self) -> str:
        """Return text used for embedding/ranking."""
        return " ".join(
            [
                self.id,
                self.name,
                self.server,
                self.category,
                self.description,
                self.schema_summary,
                " ".join(self.tags),
                " ".join(self.permissions),
                " ".join(str(value) for value in self.capabilities.values()),
            ]
        )

    def to_public_dict(self) -> dict[str, Any]:
        """Return the client-safe descriptor shape."""
        payload = asdict(self)
        payload["risk"] = self.risk_level
        payload["capabilities"] = self.capabilities or {
            "file": self.file_capable,
            "network": self.network_capable,
            "shell": self.shell_capable,
        }
        return payload


@dataclass(frozen=True)
class RankedTool:
    """A tool descriptor plus retrieval score."""

    descriptor: ToolDescriptor
    score: float


def _tokenize(text: str) -> list[str]:
    return [token.lower().replace("_", "-") for token in _WORD_RE.findall(text)]


def _vectorize(text: str) -> dict[str, float]:
    vector: dict[str, float] = {}
    for token in _tokenize(text):
        vector[token] = vector.get(token, 0.0) + 1.0
        for part in re.split(r"[-_/]", token):
            if part and part != token:
                vector[part] = vector.get(part, 0.0) + 0.5
    return vector


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0.0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class ToolRegistry:
    """Client-agnostic tool registry with JSON, SQLite, and optional Redis cache."""

    def __init__(self, cache_dir: str | Path | None = None, redis_url: str | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else Path(CACHE_DIR)
        self.cache_path = self.cache_dir / "token-slim-router-tools.json"
        self.sqlite_path = self.cache_dir / "ucr-tool-registry.sqlite3"
        self.redis_url = redis_url
        self._tools: dict[str, ToolDescriptor] = {}
        self._vectors: dict[str, dict[str, float]] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        """Register or replace one descriptor."""
        self.register_many([descriptor])

    def register_many(self, descriptors: Iterable[ToolDescriptor]) -> None:
        """Register many descriptors and persist the resulting cache."""
        for descriptor in descriptors:
            self._tools[descriptor.id] = descriptor
            self._vectors[descriptor.id] = _vectorize(descriptor.searchable_text())
        self.save_cache()

    def ingest_downstream_capabilities(self, capabilities: DownstreamCapabilities | dict[str, Any]) -> None:
        """Register downstream MCP tools discovered by the client subsystem."""
        payload = capabilities.to_dict() if isinstance(capabilities, DownstreamCapabilities) else capabilities
        server = str(payload.get("server", "downstream"))
        descriptors = [
            ToolDescriptor.from_downstream_tool(server, tool)
            for tool in payload.get("tools", [])
            if tool.get("name")
        ]
        for tool_id in [key for key, tool in self._tools.items() if tool.server == server]:
            del self._tools[tool_id]
            self._vectors.pop(tool_id, None)
        self.register_many(descriptors)

    def get(self, tool_id: str) -> ToolDescriptor | None:
        """Return a descriptor by id."""
        return self._tools.get(tool_id)

    def all(self) -> list[ToolDescriptor]:
        """Return all registered descriptors in deterministic order."""
        return [self._tools[key] for key in sorted(self._tools)]

    def rank(self, query: str, top_k: int = 8) -> list[RankedTool]:
        """Rank tools by lexical-vector relevance, with deterministic tie-breaking."""
        query_vector = _vectorize(query)
        lowered_query = query.lower()
        ranked: list[RankedTool] = []
        for descriptor in self._tools.values():
            score = _cosine(query_vector, self._vectors.get(descriptor.id, {}))
            tag_bonus = sum(0.08 for tag in descriptor.tags if tag.lower() in lowered_query)
            category_bonus = 0.05 if descriptor.category.lower() in lowered_query else 0.0
            server_bonus = 0.04 if descriptor.server.lower() in lowered_query else 0.0
            ranked.append(RankedTool(descriptor, score + tag_bonus + category_bonus + server_bonus))
        ranked.sort(key=lambda item: (-item.score, item.descriptor.id))
        return [item for item in ranked[: max(top_k, 0)] if item.score > 0.0]

    def save_cache(self) -> None:
        """Persist descriptors and vectors to JSON, SQLite, and optional Redis."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = self._payload()
        atomic_write_json(self.cache_path, payload)
        self.save_sqlite()
        self.save_redis(payload)

    def load_cache(self) -> bool:
        """Load descriptors and cached vectors from Redis, SQLite, or local JSON."""
        if self.load_redis() or self.load_sqlite():
            return True
        if not self.cache_path.exists():
            return False
        try:
            return self._load_payload(json.loads(self.cache_path.read_text()))
        except Exception as exc:
            log(f"⚠️ UCR registry JSON cache load failed: {exc}", "WARN")
            self._tools.clear()
            self._vectors.clear()
            return False

    def save_sqlite(self) -> None:
        """Persist descriptors to SQLite fallback cache."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.sqlite_path)) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS tool_descriptors "
                "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, vector TEXT NOT NULL)"
            )
            conn.execute("DELETE FROM tool_descriptors")
            conn.executemany(
                "INSERT INTO tool_descriptors (id, payload, vector) VALUES (?, ?, ?)",
                [
                    (
                        descriptor.id,
                        json.dumps(descriptor.to_public_dict(), sort_keys=True),
                        json.dumps(self._vectors.get(descriptor.id, {}), sort_keys=True),
                    )
                    for descriptor in self.all()
                ],
            )

    def load_sqlite(self) -> bool:
        """Load descriptors from SQLite fallback cache."""
        if not self.sqlite_path.exists():
            return False
        try:
            with closing(sqlite3.connect(self.sqlite_path)) as conn:
                rows = conn.execute("SELECT payload, vector FROM tool_descriptors").fetchall()
            self._tools.clear()
            self._vectors.clear()
            for payload_json, vector_json in rows:
                descriptor = ToolDescriptor.from_dict(json.loads(payload_json))
                self._tools[descriptor.id] = descriptor
                self._vectors[descriptor.id] = {
                    str(k): float(v) for k, v in json.loads(vector_json).items()
                }
            for descriptor in self._tools.values():
                self._vectors.setdefault(descriptor.id, _vectorize(descriptor.searchable_text()))
            return bool(self._tools)
        except Exception as exc:
            log(f"⚠️ UCR registry SQLite cache load failed: {exc}", "WARN")
            self._tools.clear()
            self._vectors.clear()
            return False

    def save_redis(self, payload: dict[str, Any]) -> bool:
        """Persist descriptor payload to Redis when configured and available."""
        if not self.redis_url:
            return False
        try:
            import redis

            with redis.Redis.from_url(
                self.redis_url, socket_connect_timeout=1, socket_timeout=1
            ) as client:
                client.set(
                    "context-broker:ucr:tool-registry", json.dumps(payload, ensure_ascii=False)
                )
            return True
        except Exception as exc:  # pragma: no cover - optional dependency/server
            log(f"⚠️ UCR registry Redis save skipped: {exc}", "WARN")
            return False

    def load_redis(self) -> bool:
        """Load descriptor payload from Redis when configured and available."""
        if not self.redis_url:
            return False
        try:
            import redis

            with redis.Redis.from_url(
                self.redis_url, socket_connect_timeout=1, socket_timeout=1
            ) as client:
                raw = client.get("context-broker:ucr:tool-registry")
            if not raw:
                return False
            return self._load_payload(json.loads(raw))
        except Exception as exc:  # pragma: no cover - optional dependency/server
            log(f"⚠️ UCR registry Redis load skipped: {exc}", "WARN")
            return False

    def fingerprint(self) -> str:
        """Return a stable fingerprint for cache invalidation and metrics."""
        payload = json.dumps([tool.to_public_dict() for tool in self.all()], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _payload(self) -> dict[str, Any]:
        return {
            "version": 2,
            "fingerprint": self.fingerprint(),
            "tools": [tool.to_public_dict() for tool in self.all()],
            "vectors": self._vectors,
        }

    def _load_payload(self, payload: dict[str, Any]) -> bool:
        self._tools.clear()
        self._vectors.clear()
        for tool_payload in payload.get("tools", []):
            descriptor = ToolDescriptor.from_dict(tool_payload)
            self._tools[descriptor.id] = descriptor
        raw_vectors = payload.get("vectors", {})
        for tool_id, vector in raw_vectors.items():
            if isinstance(vector, dict):
                self._vectors[tool_id] = {str(k): float(v) for k, v in vector.items()}
        for descriptor in self._tools.values():
            self._vectors.setdefault(descriptor.id, _vectorize(descriptor.searchable_text()))
        return True
