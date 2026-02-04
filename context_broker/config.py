"""
Configuration Module

Centralizes all configuration constants and environment variable handling.
This module follows the 12-factor app methodology for configuration.
"""

import os

# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================

TOTAL_CORES = os.cpu_count() or 1
"""Number of CPU cores available for parallel processing."""

# Performance optimizations for PyTorch and NumPy
os.environ["OMP_NUM_THREADS"] = str(TOTAL_CORES)
os.environ["MKL_NUM_THREADS"] = str(TOTAL_CORES)
os.environ["TORCH_NUM_THREADS"] = str(TOTAL_CORES)
os.environ["TQDM_DISABLE"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


# =============================================================================
# FILE EXTENSIONS
# =============================================================================

SUPPORTED_EXTENSIONS: list[str] = [
    # Documentation
    "*.md",
    # Configuration files
    "*.json", "*.toml", "*.yaml", "*.xml", "*.properties", "*.gradle",
    # Programming languages
    "*.go", "*.py", "*.ts", "*.js", "*.rs", "*.java",
    # Additional web files
    "*.html", "*.css", "*.scss", "*.sass", "*.less",
    # Shell and scripts
    "*.sh", "*.bash", "*.zsh", "*.fish", "*.ps1",
    # SQL and data
    "*.sql", "*.graphql", "*.prisma",
]
"""File extensions that will be indexed for semantic search."""


# =============================================================================
# IGNORED DIRECTORIES
# =============================================================================

DEFAULT_IGNORE_DIRS: set[str] = {
    # Python
    "__pycache__", ".venv", ".uv", ".tox", ".pytest_cache", ".mypy_cache",
    ".coverage", "htmlcov", ".eggs", "*.egg-info", "venv", "env", ".env",
    # Node.js
    "node_modules", ".next", ".nuxt", "dist", "build", ".output",
    # Git and VCS
    ".git", ".svn", ".hg",
    # Java/Rust/Go
    "target", "bin", "out", ".gradle",
    # IDE
    ".idea", ".vscode", ".vs", ".settings",
    # General
    ".cache", "coverage", "tmp", "temp", "logs",
}
"""Directories that are always excluded from indexing (regardless of .gitignore)."""


# =============================================================================
# PROJECT MARKERS
# =============================================================================

PROJECT_MARKERS: list[tuple[str, int]] = [
    # (marker_name, priority_score)
    # Higher scores indicate stronger project root indicators
    (".git", 100),           # Git repository - strongest indicator
    ("pyproject.toml", 50),  # Python modern
    ("package.json", 50),    # Node.js
    ("Cargo.toml", 50),      # Rust
    ("go.mod", 50),          # Go
    ("pom.xml", 40),         # Java Maven
    ("build.gradle", 40),    # Java Gradle
    ("CMakeLists.txt", 40),  # C/C++ CMake
    ("setup.py", 30),        # Legacy Python
    ("requirements.txt", 30), # Python deps
    ("Makefile", 20),        # Make
    ("Dockerfile", 20),      # Docker
    ("docker-compose.yml", 20),
    (".gitignore", 10),      # Git config
    ("README.md", 10),       # Documentation
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
    "CONTEXT_BROKER_STORAGE_DIR", 
    os.path.expanduser("~/.context-broker")
)
"""Base directory for global storage mode."""

IN_PROJECT_FOLDER: str = ".context-broker"
"""Folder name used for in-project storage."""

DEFAULT_QUERY: str = os.environ.get(
    "CONTEXT_BROKER_DEFAULT_QUERY", 
    "main entry point configuration setup"
)
"""Default query used for auto-context resource."""

DEFAULT_PROJECT_ROOT: str = os.environ.get("CONTEXT_BROKER_PROJECT_ROOT", "")
"""Default project root from environment variable."""


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


# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

CACHE_DIR: str = ".cache"
"""Directory name for cache storage."""

CACHE_FILE: str = "context-broker.json"
"""Cache file name."""
