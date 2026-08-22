"""Environment checks for the context-broker doctor.

Read-only probes that detect anything missing on the host for running this
MCP server: Python version, required/optional packages, the embedding model
cache, and external tools. Nothing here installs or modifies the system.
"""

import importlib.util
import shutil
import sys
from dataclasses import dataclass

from context_broker.config import CONTEXT_BACKEND, EMBEDDING_MODEL, REDIS_URL


@dataclass
class EnvCheck:
    """One environment probe result."""

    name: str
    status: str  # "ok" | "missing" | "warn"
    required: bool
    detail: str
    install_hint: str = ""


def _module_available(module: str) -> bool:
    """Return True when *module* can be imported, without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


# (import name, pip/uv install name)
_CORE_PACKAGES: list[tuple[str, str]] = [
    ("fastmcp", "fastmcp"),
    ("torch", "torch"),
    ("sentence_transformers", "sentence-transformers"),
    ("sklearn", "scikit-learn"),
    ("numpy", "numpy"),
    ("tiktoken", "tiktoken"),
    ("rich", "rich"),
]

_DASHBOARD_PACKAGES: list[tuple[str, str]] = [
    ("starlette", "starlette"),
    ("uvicorn", "uvicorn"),
    ("jinja2", "jinja2"),
]


def _check_python_version() -> EnvCheck:
    """Python 3.13+ is required."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 13)
    return EnvCheck(
        name="python",
        status="ok" if ok else "missing",
        required=True,
        detail=f"Python {version} (requires >= 3.13)",
        install_hint="" if ok else "Install Python 3.13+ (e.g. via uv or your OS package manager)",
    )


def _check_packages(packages: list[tuple[str, str]], *, required: bool) -> list[EnvCheck]:
    """Probe a set of importable packages."""
    checks: list[EnvCheck] = []
    for module, pip_name in packages:
        available = _module_available(module)
        checks.append(
            EnvCheck(
                name=f"package:{module}",
                status="ok" if available else "missing",
                required=required,
                detail=f"{pip_name} {'installed' if available else 'not installed'}",
                install_hint="" if available else pip_name,
            )
        )
    return checks


def _check_embedding_model() -> EnvCheck:
    """Warn when the embedding model is not in the local HF cache."""
    name = f"model:{EMBEDDING_MODEL}"
    if not _module_available("huggingface_hub"):
        return EnvCheck(
            name=name,
            status="warn",
            required=False,
            detail="huggingface_hub unavailable; cannot inspect model cache",
        )
    try:
        from huggingface_hub import scan_cache_dir

        cached = {repo.repo_id for repo in scan_cache_dir().repos}
    except Exception as e:
        return EnvCheck(
            name=name,
            status="warn",
            required=False,
            detail=f"Could not inspect HuggingFace cache: {e}",
        )
    wanted = EMBEDDING_MODEL.rsplit("/", 1)[-1]
    hit = any(repo.rsplit("/", 1)[-1] == wanted for repo in cached)
    return EnvCheck(
        name=name,
        status="ok" if hit else "warn",
        required=False,
        detail=(
            f"'{EMBEDDING_MODEL}' found in local cache"
            if hit
            else f"'{EMBEDDING_MODEL}' not cached; first index run will download it"
        ),
    )


def _check_executable(binary: str, *, purpose: str) -> EnvCheck:
    """Probe an external executable on PATH."""
    path = shutil.which(binary)
    return EnvCheck(
        name=f"binary:{binary}",
        status="ok" if path else "warn",
        required=False,
        detail=f"{binary} found at {path}" if path else f"{binary} not on PATH ({purpose})",
        install_hint="" if path else f"Install {binary} ({purpose})",
    )


def run_checks() -> list[EnvCheck]:
    """Run every environment probe and return results in stable order."""
    checks: list[EnvCheck] = [_check_python_version()]
    checks.extend(_check_packages(_CORE_PACKAGES, required=True))

    if CONTEXT_BACKEND == "honcho":
        checks.extend(_check_packages([("honcho", "honcho-ai")], required=True))
    if CONTEXT_BACKEND == "redis" or REDIS_URL:
        checks.extend(_check_packages([("redis", "redis")], required=True))

    checks.extend(_check_packages(_DASHBOARD_PACKAGES, required=False))
    checks.append(_check_embedding_model())
    checks.append(_check_executable("git", purpose="changelog tools"))
    checks.append(_check_executable("uv", purpose="package installs"))
    return checks
