"""
Configuration Module

Centralizes all configuration constants and environment variable handling.
This module follows the 12-factor app methodology for configuration.
"""

import os


def _get_env_int(name: str, default: int) -> int:
    """Parse an integer env var with a safe fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    """Parse a float env var with a safe fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================

TOTAL_CORES = os.cpu_count() or 1
"""Number of CPU cores available for parallel processing."""
WORKER_CORES = max(1, TOTAL_CORES // 2)
"""Number of CPU cores used for indexing/search (half of available cores)."""
MODEL_LOCAL_ONLY: bool = os.environ.get("CONTEXT_BROKER_LOCAL_ONLY", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
"""Prefer cache-only model loading, with one bootstrap download on a cache miss."""

# Performance optimizations for PyTorch and NumPy
os.environ["OMP_NUM_THREADS"] = str(WORKER_CORES)
os.environ["MKL_NUM_THREADS"] = str(WORKER_CORES)
os.environ["TORCH_NUM_THREADS"] = str(WORKER_CORES)
os.environ["TQDM_DISABLE"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


# =============================================================================
# FILE EXTENSIONS
# =============================================================================

SUPPORTED_EXTENSIONS: list[str] = [
    # Documentation
    "*.md",
    # Configuration files
    "*.json",
    "*.toml",
    "*.yaml",
    "*.xml",
    "*.properties",
    "*.gradle",
    # Programming languages
    "*.go",
    "*.py",
    "*.ts",
    "*.js",
    "*.rs",
    "*.java",
    # Additional web files
    "*.html",
    "*.css",
    "*.scss",
    "*.sass",
    "*.less",
    # Shell and scripts
    "*.sh",
    "*.bash",
    "*.zsh",
    "*.fish",
    "*.ps1",
    # SQL and data
    "*.sql",
    "*.graphql",
    "*.prisma",
]
"""File extensions that will be indexed for semantic search.

NOTE: .env files and other secret-bearing files are EXPLICITLY excluded via
SECRET_FILE_PATTERNS below. They are never indexed or returned to AI providers,
even if present in supported directories or matched by glob patterns.
"""


# =============================================================================
# SECURITY: SECRET FILE PROTECTION
# =============================================================================
# These patterns define files that MUST NEVER be indexed or sent to external
# AI providers because they commonly contain secrets, credentials, tokens,
# passwords, API keys, private keys, or other sensitive data.
#
# This is a defense-in-depth measure. Even if .gitignore fails to exclude
# these files, or if they are explicitly tracked, they will be hard-blocked
# by the indexing and search pipeline.
#
# The patterns are matched against:
#   - File basename (e.g., ".env")
#   - Full relative path (e.g., "config/secrets.yml")
#   - Content signatures (see SECRET_ENV_KEY_PATTERNS)
#
# When a file is blocked, a security audit log is emitted and the file is
# silently skipped. No content is read, embedded, or returned.
# =============================================================================

SECRET_FILE_PATTERNS: set[str] = {
    # Environment files (all variants)
    ".env",
    ".env.*",
    "*.env",
    "*.env.*",
    # AWS credentials
    ".aws/credentials",
    ".aws/config",
    # SSH / TLS private keys
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    # Kubernetes secrets
    "*.kubeconfig",
    "kubeconfig",
    # Docker registry auth
    ".docker/config.json",
    # Pip auth
    ".pypirc",
    # Git credentials
    ".git-credentials",
    # Terraform state (may contain secrets)
    "*.tfstate",
    "*.tfstate.*",
    # Database dumps
    "*.dump",
    "*.sql.dump",
    # Known secret filenames
    "secrets.*",
    "secret.*",
    "*.secrets",
    "*.secret",
    "credentials.*",
    "*.credentials",
    "*.token",
    "*.tokens",
    "api_key*",
    "apikey*",
    "private_key*",
    "privatekey*",
}
"""Files/directories that must NEVER be indexed or returned to AI providers.

These patterns are hard-coded and cannot be overridden by .gitignore or
user configuration. They provide a safety net against accidental secret leakage.
"""

SECRET_ENV_KEY_PATTERNS: set[str] = {
    "PRIVATE_KEY",
    "SECRET_KEY",
    "API_KEY",
    "ACCESS_KEY",
    "AUTH_TOKEN",
    "PASSWORD",
    "SECRET",
    "CREDENTIAL",
    "TOKEN=",
    "KEY=",
    "SECRET=",
    "PASSWORD=",
    # NPM / Yarn auth tokens in .npmrc / .yarnrc
    "_authToken",
    "_auth",
    # Bearer tokens
    "Bearer ",
}
"""Content signatures that trigger secret-file detection when found in files.

If a file contains lines matching these patterns, it is treated as a secret
file and blocked from indexing regardless of filename. This catches renamed
.env files and other secret-bearing files.
"""


# =============================================================================
# IGNORED DIRECTORIES
# =============================================================================

DEFAULT_IGNORE_DIRS: set[str] = {
    # Python
    "__pycache__",
    ".venv",
    ".uv",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".coverage",
    "htmlcov",
    ".eggs",
    "*.egg-info",
    "venv",
    "env",
    ".env",
    # Node.js
    "node_modules",
    ".next",
    ".nuxt",
    "dist",
    "build",
    ".output",
    # Git and VCS
    ".git",
    ".svn",
    ".hg",
    # Java/Rust/Go
    "target",
    "bin",
    "out",
    ".gradle",
    # IDE
    ".idea",
    ".vscode",
    ".vs",
    ".settings",
    # General
    ".cache",
    ".context-broker",
    "coverage",
    "tmp",
    "temp",
    "logs",
}
"""Directories that are always excluded from indexing (regardless of .gitignore)."""


# =============================================================================
# PROJECT MARKERS
# =============================================================================

PROJECT_MARKERS: list[tuple[str, int]] = [
    # (marker_name, priority_score)
    # Higher scores indicate stronger project root indicators
    (".git", 100),  # Git repository - strongest indicator
    ("pyproject.toml", 50),  # Python modern
    ("package.json", 50),  # Node.js
    ("Cargo.toml", 50),  # Rust
    ("go.mod", 50),  # Go
    ("pom.xml", 40),  # Java Maven
    ("build.gradle", 40),  # Java Gradle
    ("CMakeLists.txt", 40),  # C/C++ CMake
    ("setup.py", 30),  # Legacy Python
    ("requirements.txt", 30),  # Python deps
    ("Makefile", 20),  # Make
    ("Dockerfile", 20),  # Docker
    ("docker-compose.yml", 20),
    (".gitignore", 10),  # Git config
    ("README.md", 10),  # Documentation
    ("LICENSE", 10),
]
"""Files/directories that indicate a project root, with priority scores."""


# =============================================================================
# STORAGE CONFIGURATION
# =============================================================================


class StorageMode:
    """Storage mode constants."""

    GLOBAL = "global"
    IN_PROJECT = "in-project"
    BOTH = "both"


# Get storage configuration from environment
STORAGE_MODE: str = os.environ.get("CONTEXT_BROKER_STORAGE_MODE", StorageMode.BOTH)
"""Storage mode: 'global', 'in-project', or 'both'."""

STORAGE_BASE_DIR: str = os.environ.get(
    "CONTEXT_BROKER_STORAGE_DIR", os.path.expanduser("~/.context-broker")
)
"""Base directory for global storage mode."""

IN_PROJECT_FOLDER: str = ".context-broker"
"""Folder name used for in-project storage."""
TOKEN_COUNTER_SUBDIR: str = "_internal"
"""Internal subdirectory for token counter persistence."""
TOKEN_COUNTER_FILENAME: str = "token-counter-latest.json"
"""Filename for the latest persisted token counter report."""
TOKEN_COUNTER_RUNS_SUBDIR: str = "_internal/token-runs"
"""Internal subdirectory for append-only token counter run reports."""

DEFAULT_QUERY: str = os.environ.get(
    "CONTEXT_BROKER_DEFAULT_QUERY", "main entry point configuration setup"
)
"""Default query used for auto-context resource."""

DEFAULT_PROJECT_ROOT: str = os.environ.get("CONTEXT_BROKER_PROJECT_ROOT", "")
"""Default project root from environment variable."""
ENABLE_PROGRESS_NOTIFICATIONS: bool = os.environ.get(
    "CONTEXT_BROKER_ENABLE_PROGRESS_NOTIFICATIONS", "1"
).lower() in {"1", "true", "yes", "on"}
"""Enable MCP progress notifications (token summaries visible in MCP clients). Set 0 to reduce chatter/latency."""


# =============================================================================
# TRANSPORT CONFIGURATION
# =============================================================================

TRANSPORT: str = os.environ.get("CONTEXT_BROKER_TRANSPORT", "stdio")
"""Transport protocol: 'stdio', 'sse', 'streamable-http', or 'ws'."""

HOST: str = os.environ.get("CONTEXT_BROKER_HOST", "0.0.0.0")
"""Host address for network transports (sse, streamable-http, ws)."""

PORT: int = int(os.environ.get("CONTEXT_BROKER_PORT", "8765"))
"""Port for network transports (sse, streamable-http, ws)."""

EXIT_WHEN_PARENT_DIES: bool = os.environ.get(
    "CONTEXT_BROKER_EXIT_WHEN_PARENT_DIES",
    "1",
).lower() in {"1", "true", "yes", "on"}
"""Exit automatically when the launching editor/host process disappears."""

PARENT_POLL_INTERVAL_SECONDS: float = max(
    0.5,
    _get_env_float("CONTEXT_BROKER_PARENT_POLL_INTERVAL_SECONDS", 3.0),
)
"""How often to poll the startup parent chain for orphan detection."""

IDLE_RESOURCE_TIMEOUT_SECONDS: int = max(
    0,
    _get_env_int("CONTEXT_BROKER_IDLE_RESOURCE_TIMEOUT_SECONDS", 900),
)
"""Release in-memory indexes/models after this many idle seconds (0 disables)."""

IDLE_RESOURCE_CLEANUP_INTERVAL_SECONDS: float = max(
    5.0,
    _get_env_float("CONTEXT_BROKER_IDLE_RESOURCE_CLEANUP_INTERVAL_SECONDS", 30.0),
)
"""How often to check whether idle resources should be released."""


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

EMBEDDING_MODEL: str = os.environ.get(
    "CONTEXT_BROKER_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)
"""Sentence transformer model used for embeddings.

Configurable via CONTEXT_BROKER_EMBEDDING_MODEL. Any model compatible with
the ``sentence-transformers`` library works — e.g. ``all-mpnet-base-v2``
for higher quality, or ``paraphrase-MiniLM-L3-v2`` for faster searches.
Must be pre-downloaded when CONTEXT_BROKER_LOCAL_ONLY is enabled.
"""

ENCODING_MODEL: str = "cl100k_base"
"""Tiktoken encoding model for token counting."""

MODEL_DEVICE: str = os.environ.get("CONTEXT_BROKER_DEVICE", "cpu")
"""Torch device for the embedding model (e.g. "cpu", "cuda", "mps")."""

# ---------------------------------------------------------------------------
# Optional LLM configuration
# ---------------------------------------------------------------------------
# These settings have **no built-in effect** yet — they are exposed so MCP
# clients and future tools can discover what LLM endpoint / model to use.
# Set them in your .env or MCP client env block and read them from the
# ``get_storage_config`` tool response.
# ---------------------------------------------------------------------------

LLM_MODEL: str = os.environ.get("CONTEXT_BROKER_LLM_MODEL", "")
"""Optional LLM model identifier (e.g. "llama3", "gpt-4o", "claude-3-opus").
Exposed via the storage-config tool so MCP clients can discover it."""

LLM_BASE_URL: str = os.environ.get("CONTEXT_BROKER_LLM_BASE_URL", "")
"""Optional base URL for an LLM API endpoint (e.g. "http://localhost:11434/v1"
for Ollama, or an OpenAI-compatible endpoint)."""

LLM_API_KEY: str = os.environ.get("CONTEXT_BROKER_LLM_API_KEY", "")
"""Optional API key for the LLM endpoint. Leave empty for local models."""

DEFAULT_TOP_K: int = 5
"""Default number of search results to return."""

BATCH_SIZE: int = 32
"""Batch size for embedding generation."""
INDEX_FILE_MAX_CHARS: int = int(os.environ.get("CONTEXT_BROKER_INDEX_FILE_MAX_CHARS", "12000"))
"""Maximum characters read per file for indexing/token estimation."""
RESULT_FILE_MAX_CHARS: int = int(os.environ.get("CONTEXT_BROKER_RESULT_FILE_MAX_CHARS", "40000"))
"""Maximum characters read per file before snippet extraction."""
RESULT_SNIPPET_WINDOW_CHARS: int = int(
    os.environ.get("CONTEXT_BROKER_RESULT_SNIPPET_WINDOW_CHARS", "3000")
)
"""Character window around the most relevant query term per file."""
RESULT_MAX_TOKENS_PER_FILE: int = int(
    os.environ.get("CONTEXT_BROKER_RESULT_MAX_TOKENS_PER_FILE", "700")
)
"""Hard token cap per returned file snippet."""


# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

CACHE_DIR: str = ".cache"
"""Directory name for cache storage."""

CACHE_FILE: str = "context-broker.json"
"""Cache file name."""

# Query cache is always persisted as local JSON.


# =============================================================================
# REDIS CONFIGURATION (used by the Redis cross-chat context backend only)
# =============================================================================

REDIS_URL: str = os.environ.get("CONTEXT_BROKER_REDIS_URL", "")
"""Redis connection URL used when CONTEXT_BROKER_CONTEXT_BACKEND=redis."""

REDIS_KEY_PREFIX: str = os.environ.get("CONTEXT_BROKER_REDIS_KEY_PREFIX", "context-broker")
"""Prefix for Redis keys so multiple deployments can share one Redis instance safely."""

CHAT_CACHE_TTL_SECONDS: int = max(
    0, _get_env_int("CONTEXT_BROKER_CHAT_CACHE_TTL_SECONDS", 300)
)
"""TTL for the Redis chat-payload cache (entries from load_chat_context).

0 disables the cache. Active whenever CONTEXT_BROKER_REDIS_URL is set, regardless
of which cross-chat context backend is selected.
"""

AUTO_WARM_CACHE_ON_SAVE: bool = os.environ.get(
    "CONTEXT_BROKER_AUTO_WARM_CACHE_ON_SAVE", "1"
).lower() in {"1", "true", "yes", "on"}
"""When enabled (the default), every save_chat_context / record_turn call
invalidates the per-session cache entries AND immediately warms the
default-params signature with the freshly persisted session. So a load right
after a save is a cached hit instead of a miss-then-fill round trip.

Set to 0 to fall back to invalidate-only behavior.
"""


# =============================================================================
# CROSS-CHAT CONTEXT CONFIGURATION
# =============================================================================

CONTEXT_BACKEND: str = os.environ.get("CONTEXT_BROKER_CONTEXT_BACKEND", "none").lower()
"""Cross-chat context backend: 'none', 'honcho', or 'redis'.

'redis' uses Redis as a Honcho-equivalent store for cross-session context
sharing — messages are keyed by project + session_id and survive across chats.
"""

HONCHO_WORKSPACE_ID: str = os.environ.get("CONTEXT_BROKER_HONCHO_WORKSPACE_ID", "context-broker")
"""Honcho workspace id used when CONTEXT_BROKER_CONTEXT_BACKEND=honcho."""

HONCHO_SESSION_PREFIX: str = os.environ.get("CONTEXT_BROKER_HONCHO_SESSION_PREFIX", "context-broker")
"""Prefix applied to Honcho session ids created by this MCP server."""

HONCHO_USER_PEER_ID: str = os.environ.get("CONTEXT_BROKER_HONCHO_USER_PEER_ID", "user")
"""Default Honcho peer id for user-authored messages."""

HONCHO_ASSISTANT_PEER_ID: str = os.environ.get(
    "CONTEXT_BROKER_HONCHO_ASSISTANT_PEER_ID", "assistant"
)
"""Default Honcho peer id for assistant-authored messages."""

HONCHO_CONTEXT_TOKENS: int = max(1, _get_env_int("CONTEXT_BROKER_HONCHO_CONTEXT_TOKENS", 2000))
"""Default token budget when loading Honcho session context."""

HONCHO_LIMIT_TO_SESSION: bool = os.environ.get(
    "CONTEXT_BROKER_HONCHO_LIMIT_TO_SESSION", "1"
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
"""Limit Honcho representation/search context to the selected session by default."""


# ---------------------------------------------------------------------------
# USER IDENTITY (who is asking the question?)
# ---------------------------------------------------------------------------

USE_ACCOUNT_NAME: bool = os.environ.get(
    "CONTEXT_BROKER_USE_ACCOUNT_NAME", "0"
).lower() in {"1", "true", "yes", "on"}
"""When enabled, default the user peer id to the OS account name instead of
``HONCHO_USER_PEER_ID`` ('user'). Only affects the user peer — assistant stays
generic. Explicit ``user_peer_id`` arguments to ``save_chat_context`` /
``load_chat_context`` always win.
"""

ACCOUNT_NAME_OVERRIDE: str = os.environ.get("CONTEXT_BROKER_ACCOUNT_NAME_OVERRIDE", "")
"""Explicit override for the resolved account name. Takes priority over
``getpass.getuser()`` when ``CONTEXT_BROKER_USE_ACCOUNT_NAME`` is enabled.
"""


# =============================================================================
# DASHBOARD CONFIGURATION (web-only cross-chat viewer)
# =============================================================================

DASHBOARD_HOST: str = os.environ.get("CONTEXT_BROKER_DASHBOARD_HOST", "127.0.0.1")
"""Host bind address for the web-only cross-chat dashboard."""

DASHBOARD_PORT: int = int(os.environ.get("CONTEXT_BROKER_DASHBOARD_PORT", "8770"))
"""Port for the web-only cross-chat dashboard."""
