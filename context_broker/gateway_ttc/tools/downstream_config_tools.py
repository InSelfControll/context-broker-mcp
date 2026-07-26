"""Secret-safe configuration loading for gateway downstream MCP servers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from context_broker.client_ttc.tools.contract_tools import (
    DownstreamServerConfig,
    DownstreamTransport,
    validate_downstream_identity,
)

_CONFIG_VERSION = "ucr.gateway_downstreams.v1"
_ENV_REFERENCE_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_OBVIOUS_SECRET_RE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|(?:sk|gh[pousr]|glpat|xox[baprs])[-_][A-Za-z0-9_-]{8,})"
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:api[-_]?key|access[-_]?key|access[-_]?token|auth(?:orization)?|"
    r"client[-_]?secret|credential|password|secret|token)\s*[:=]\s*\S+"
)
_SENSITIVE_ARGUMENT_NAMES = {
    "access-key",
    "access-token",
    "api-key",
    "auth",
    "auth-token",
    "authorization",
    "client-secret",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
_SERVER_FIELDS = {
    "name",
    "transport",
    "command",
    "args",
    "env",
    "url",
    "headers",
    "timeout_seconds",
    "heartbeat_interval_seconds",
    "reconnect_attempts",
    "reconnect_backoff_seconds",
}


def _is_env_file(path: Path) -> bool:
    """Return whether a path names an environment file that must never be read."""
    lowered = path.name.lower()
    return lowered == ".env" or lowered.startswith(".env.") or lowered.endswith(".env")


def _require_optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"downstream server {key} must be a string")
    return value


def _require_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"downstream server {key} must be an array of strings")
    return list(value)


def _normalized_option_name(value: str) -> str:
    """Normalize a URL query key or command option for sensitive-name checks."""
    return value.lstrip("-").split("=", 1)[0].replace("_", "-").lower()


def _is_sensitive_name(value: str) -> bool:
    """Return whether a field name is conventionally credential-bearing."""
    normalized = _normalized_option_name(value)
    compact = normalized.replace("-", "")
    sensitive_compact = {
        name.replace("-", "") for name in _SENSITIVE_ARGUMENT_NAMES
    }
    return (
        normalized in _SENSITIVE_ARGUMENT_NAMES
        or compact in sensitive_compact
        or any(normalized.endswith(f"-{name}") for name in _SENSITIVE_ARGUMENT_NAMES)
    )


def _validate_credential_free_url(url: str | None) -> None:
    """Reject URL locations that embed credentials instead of using headers."""
    if url is None:
        return
    try:
        parsed = urlsplit(url)
        username = parsed.username
        password = parsed.password
    except ValueError:
        raise ValueError("downstream server url is invalid") from None
    if username is not None or password is not None:
        raise ValueError("downstream server url must not contain userinfo credentials")
    if any(
        _is_sensitive_name(name)
        for name, _value in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        raise ValueError("downstream server url must not contain credential query parameters")
    if _OBVIOUS_SECRET_RE.search(url):
        raise ValueError("downstream server url must not contain an inline credential")


def _validate_credential_free_arguments(arguments: list[str]) -> None:
    """Reject argv entries that conventionally carry inline credentials."""
    for argument in arguments:
        if (
            _is_sensitive_name(argument)
            or _OBVIOUS_SECRET_RE.search(argument)
            or _CREDENTIAL_ASSIGNMENT_RE.search(argument)
        ):
            raise ValueError(
                "downstream server args must not contain credential flags or values"
            )


def _require_float(
    payload: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"downstream server {key} must be a number")
    parsed = float(value)
    if parsed < minimum:
        raise ValueError(f"downstream server {key} must be at least {minimum}")
    return parsed


def _require_int(
    payload: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"downstream server {key} must be an integer")
    if value < minimum:
        raise ValueError(f"downstream server {key} must be at least {minimum}")
    return value


def _resolve_reference_map(
    payload: dict[str, Any],
    field_name: str,
    environ: Mapping[str, str],
) -> dict[str, str]:
    raw_mapping = payload.get(field_name, {})
    if not isinstance(raw_mapping, dict):
        raise ValueError(f"downstream server {field_name} must be an object")

    resolved: dict[str, str] = {}
    for raw_key, raw_reference in raw_mapping.items():
        if not isinstance(raw_key, str) or not isinstance(raw_reference, str):
            raise ValueError(
                f"downstream server {field_name} keys and values must be strings"
            )
        match = _ENV_REFERENCE_RE.fullmatch(raw_reference)
        if match is None:
            raise ValueError(
                f"downstream server {field_name}.{raw_key} must be an "
                "environment reference in ${VARIABLE_NAME} form"
            )
        variable_name = match.group(1)
        if variable_name not in environ:
            raise ValueError(
                f"required injected environment variable {variable_name} is not set"
            )
        resolved[raw_key] = environ[variable_name]
    return resolved


def _build_server_config(
    payload: dict[str, Any],
    environ: Mapping[str, str],
) -> DownstreamServerConfig:
    unknown_fields = sorted(set(payload) - _SERVER_FIELDS)
    if unknown_fields:
        raise ValueError(
            f"downstream server has unsupported fields: {', '.join(unknown_fields)}"
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("downstream server name is required")
    validate_downstream_identity(name, kind="server name")
    raw_transport = payload.get("transport")
    if not isinstance(raw_transport, str):
        raise ValueError("downstream server transport is required")
    try:
        transport = DownstreamTransport(raw_transport)
    except ValueError:
        raise ValueError(
            "downstream server transport must be one of: stdio, http, sse"
        ) from None

    command = _require_optional_string(payload, "command")
    args = _require_string_list(payload, "args")
    url = _require_optional_string(payload, "url")
    _validate_credential_free_arguments(args)
    _validate_credential_free_url(url)

    config = DownstreamServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=args,
        env=_resolve_reference_map(payload, "env", environ),
        url=url,
        headers=_resolve_reference_map(payload, "headers", environ),
        timeout_seconds=_require_float(
            payload,
            "timeout_seconds",
            30.0,
            minimum=0.001,
        ),
        heartbeat_interval_seconds=_require_float(
            payload,
            "heartbeat_interval_seconds",
            30.0,
            minimum=0.001,
        ),
        reconnect_attempts=_require_int(
            payload,
            "reconnect_attempts",
            3,
            minimum=0,
        ),
        reconnect_backoff_seconds=_require_float(
            payload,
            "reconnect_backoff_seconds",
            0.25,
            minimum=0.0,
        ),
    )
    config.validate()
    return config


def load_downstream_server_configs(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[DownstreamServerConfig]:
    """Load and validate downstream configs without accepting persisted secrets."""
    path = Path(config_path)
    if path.is_symlink():
        raise ValueError("symlink downstream configuration paths are not allowed")
    if _is_env_file(path):
        raise ValueError(".env files cannot be used as downstream configuration")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("downstream configuration must contain valid JSON") from None
    except OSError:
        raise ValueError(f"unable to read downstream configuration: {path}") from None

    if not isinstance(payload, dict):
        raise ValueError("downstream configuration must be a JSON object")
    if payload.get("version") != _CONFIG_VERSION:
        raise ValueError(f"downstream configuration version must be {_CONFIG_VERSION}")
    unknown_root_fields = sorted(set(payload) - {"version", "servers"})
    if unknown_root_fields:
        raise ValueError(
            f"downstream configuration has unsupported fields: "
            f"{', '.join(unknown_root_fields)}"
        )
    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, list):
        raise ValueError("downstream configuration servers must be an array")

    active_environment = os.environ if environ is None else environ
    configs: list[DownstreamServerConfig] = []
    names: set[str] = set()
    for raw_server in raw_servers:
        if not isinstance(raw_server, dict):
            raise ValueError("each downstream server must be a JSON object")
        config = _build_server_config(raw_server, active_environment)
        if config.name in names:
            raise ValueError(f"duplicate downstream server name: {config.name}")
        names.add(config.name)
        configs.append(config)
    return configs
