"""
Utility Functions

Shared utility functions for logging, token counting, and path handling.
"""

import sys
from pathlib import Path
from typing import Optional

import tiktoken


def log(message: str, level: str = "INFO") -> None:
    """
    Write a log message to stderr.
    
    Using stderr keeps logs separate from the MCP protocol messages on stdout.
    
    Args:
        message: The message to log
        level: Log level (INFO, WARN, ERROR)
    """
    prefix = "[Broker]"
    if level != "INFO":
        prefix = f"[Broker:{level}]"
    sys.stderr.write(f"{prefix} {message}\n")
    sys.stderr.flush()


def log_ascii_table(
    project_name: str, 
    total_tokens: int, 
    sent_tokens: int, 
    saved_tokens: int, 
    saved_percent: float
) -> None:
    """
    Display token usage statistics in an ASCII table format.
    
    This table is only displayed in logs - the AI never sees it directly.
    
    Args:
        project_name: Name of the project
        total_tokens: Total tokens in the project
        sent_tokens: Tokens sent in the current context
        saved_tokens: Tokens saved by selective context
        saved_percent: Percentage of tokens saved
    """
    box = f"""
[Broker] +-------------------------------------------------------+
[Broker] | 📊 TOKEN REPORT: {project_name:<29} |
[Broker] +-------------------------------------------------------+
[Broker] | 🗂️  Total Project : {total_tokens:>10,} tokens                |
[Broker] | 📤  Context Sent  : {sent_tokens:>10,} tokens                |
[Broker] | 💰  TOKENS SAVED  : {saved_tokens:>10,} ({saved_percent:>5.1f}%)         |
[Broker] +-------------------------------------------------------+
"""
    sys.stderr.write(box)
    sys.stderr.flush()


def count_tokens(text: str, encoder: tiktoken.Encoding) -> int:
    """
    Count the number of tokens in a text string.
    
    Args:
        text: The text to count tokens for
        encoder: Tiktoken encoding instance
        
    Returns:
        Number of tokens, or estimated count if encoding fails
    """
    try:
        return len(encoder.encode(text))
    except Exception:
        # Fallback: rough estimate (1 token ≈ 4 characters for English)
        return len(text) // 4


def get_cache_path(project_root: str | Path) -> Path:
    """
    Get the cache file path for a project.
    
    Args:
        project_root: Path to the project root
        
    Returns:
        Path to the cache file
    """
    cache_dir = Path(project_root) / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "context-broker.json"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for filesystem storage.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename with .json extension
    """
    # Remove any path components
    filename = Path(filename).name
    
    # Ensure .json extension
    if not filename.endswith(".json"):
        filename = filename + ".json"
    
    return filename
