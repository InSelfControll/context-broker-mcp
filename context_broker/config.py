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
MODEL_LOCAL_ONLY: bool = os.environ.get("CONTEXT_BROKER_LOCAL_ONLY", "1").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
"""If enabled, embedding model loading is strictly local-only (no network fetch)."""

if MODEL_LOCAL_ONLY:
    # Force local/offline behavior for HuggingFace-backed model loading.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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
"""File extensions that will be indexed for semantic search."""


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

DEFAULT_QUERY: str = os.environ.get(
    "CONTEXT_BROKER_DEFAULT_QUERY", "main entry point configuration setup"
)
"""Default query used for auto-context resource."""

DEFAULT_PROJECT_ROOT: str = os.environ.get("CONTEXT_BROKER_PROJECT_ROOT", "")
"""Default project root from environment variable."""
ENABLE_PROGRESS_NOTIFICATIONS: bool = os.environ.get(
    "CONTEXT_BROKER_ENABLE_PROGRESS_NOTIFICATIONS", "0"
).lower() in {"1", "true", "yes", "on"}
"""Enable MCP progress notifications (disabled by default for lower latency)."""


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

EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
"""Sentence transformer model used for embeddings."""

ENCODING_MODEL: str = "cl100k_base"
"""Tiktoken encoding model for token counting."""

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
