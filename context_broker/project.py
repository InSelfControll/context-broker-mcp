"""
Project Detection and Path Resolution

Handles project root auto-detection, ignore pattern parsing, and path utilities.
"""

import fnmatch
import os
from pathlib import Path
from typing import Optional

from context_broker.config import PROJECT_MARKERS, DEFAULT_IGNORE_DIRS
from context_broker.utils import log


def parse_ignore_file(filepath: Path) -> list[str]:
    """
    Parse a .gitignore or .dockerignore file and return list of patterns.
    
    Handles:
    - Comments (lines starting with #)
    - Negations (lines starting with !)
    - Directory markers (trailing /)
    - Blank lines
    - Whitespace trimming
    
    Args:
        filepath: Path to the ignore file
        
    Returns:
        List of valid ignore patterns
    """
    patterns: list[str] = []
    
    if not filepath.exists():
        return patterns
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                original_line = line
                line = line.rstrip("\n\r")
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Handle negation patterns (e.g., !important.log)
                # These are collected but processed differently in should_ignore
                patterns.append(line)
                
    except Exception as e:
        log(f"⚠️ Error reading ignore file {filepath}: {e}", "WARN")
    
    return patterns


def should_ignore(
    path: str, 
    rel_path: str, 
    patterns: list[str], 
    ignore_dirs: set[str]
) -> bool:
    """
    Check if a path should be ignored based on patterns and ignored directories.
    
    This implements gitignore-style pattern matching with support for:
    - Directory-only patterns (trailing /)
    - Negation patterns (leading !)
    - Wildcards (* and **)
    - Anchored patterns (leading /)
    
    Args:
        path: Absolute path to file/directory
        rel_path: Path relative to project root
        patterns: List of gitignore-style patterns
        ignore_dirs: Set of directory names to always ignore
        
    Returns:
        True if the path should be ignored
    """
    path_parts = Path(path).parts
    
    # Check default ignored directories first (highest priority)
    for part in path_parts:
        if part in ignore_dirs:
            return True
    
    # Process patterns in order (later patterns can override earlier ones)
    ignored = False
    
    for pattern in patterns:
        # Handle negation
        negated = pattern.startswith("!")
        if negated:
            pattern = pattern[1:]
        
        # Skip empty patterns after removing negation
        if not pattern:
            continue
        
        # Determine if this is an anchored pattern (starts with /)
        anchored = pattern.startswith("/")
        clean_pattern = pattern.lstrip("/").rstrip("/")
        
        # Check for directory-only pattern
        is_dir_pattern = pattern.endswith("/")
        
        # Match against the path
        matched = False
        
        # Handle ** wildcards (matches any number of directories)
        if "**" in clean_pattern:
            matched = _match_double_star(rel_path, clean_pattern)
        # Handle anchored patterns (must match from start)
        elif anchored:
            matched = fnmatch.fnmatch(rel_path, clean_pattern)
        # Handle basename-only patterns
        else:
            basename = os.path.basename(rel_path)
            matched = fnmatch.fnmatch(rel_path, clean_pattern) or \
                      fnmatch.fnmatch(basename, clean_pattern)
        
        # Handle directory patterns
        if matched and is_dir_pattern:
            # Check if this is actually a directory or if the path starts with this
            if not (rel_path.startswith(clean_pattern + os.sep) or 
                    rel_path == clean_pattern):
                matched = False
        
        # Apply negation logic
        if matched:
            ignored = not negated
    
    return ignored


def _match_double_star(path: str, pattern: str) -> bool:
    """
    Match a path against a pattern containing ** wildcards.
    
    ** matches zero or more directories.
    
    Args:
        path: The path to match
        pattern: Pattern containing **
        
    Returns:
        True if the path matches the pattern
    """
    # Convert ** pattern to a simpler form
    parts = pattern.split("/**/")
    
    if len(parts) == 1:
        # Pattern is like "**/file" or "dir/**"
        if pattern.startswith("**/"):
            # Match any depth
            suffix = pattern[3:]
            return fnmatch.fnmatch(os.path.basename(path), suffix) or \
                   any(fnmatch.fnmatch("/".join(path.split("/")[i:]), suffix) 
                       for i in range(len(path.split("/"))))
        else:
            # Pattern is "dir/**" - match anything under dir
            prefix = pattern.rstrip("/**")
            return path.startswith(prefix)
    
    # Pattern has ** in the middle: "prefix/**/suffix"
    prefix, suffix = parts[0], parts[1]
    
    if not path.startswith(prefix):
        return False
    
    # Check suffix matches somewhere after prefix
    remaining = path[len(prefix):].lstrip("/")
    path_parts = remaining.split("/")
    
    for i in range(len(path_parts)):
        candidate = "/".join(path_parts[i:])
        if fnmatch.fnmatch(candidate, suffix) or \
           fnmatch.fnmatch(candidate, suffix.lstrip("/")):
            return True
    
    return False


def load_ignore_patterns(project_root: str | Path) -> list[str]:
    """
    Load ignore patterns from .gitignore and .dockerignore files.
    
    Returns combined list of patterns from both files.
    
    Args:
        project_root: Path to the project root
        
    Returns:
        Combined list of ignore patterns
    """
    patterns: list[str] = []
    project_root = Path(project_root)
    
    # Load .gitignore
    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        gitignore_patterns = parse_ignore_file(gitignore_path)
        patterns.extend(gitignore_patterns)
        log(f"📄 Loaded {len(gitignore_patterns)} patterns from .gitignore")
    
    # Load .dockerignore
    dockerignore_path = project_root / ".dockerignore"
    if dockerignore_path.exists():
        dockerignore_patterns = parse_ignore_file(dockerignore_path)
        patterns.extend(dockerignore_patterns)
        log(f"📄 Loaded {len(dockerignore_patterns)} patterns from .dockerignore")
    
    return patterns


def find_project_root(start_path: str | Path = "") -> Optional[str]:
    """
    Auto-detect project root by looking for marker files.
    
    Traverses up from start_path (or CWD) until it finds markers.
    Returns the path with the highest score (most markers found).
    
    Args:
        start_path: Starting path for traversal (defaults to CWD)
        
    Returns:
        Path to the detected project root, or None if not found
    """
    if not start_path:
        start_path = os.getcwd()
    
    start_path = Path(start_path).resolve()
    current = start_path
    
    best_root: Optional[Path] = None
    best_score = 0
    
    # Walk up the directory tree
    while current != current.parent:
        score = 0
        
        for marker, points in PROJECT_MARKERS:
            marker_path = current / marker
            if marker_path.exists():
                score += points
        
        if score > best_score:
            best_score = score
            best_root = current
            
            # If we found a .git (score >= 100), this is definitely the root
            if score >= 100:
                break
        
        current = current.parent
    
    return str(best_root) if best_root else None


def resolve_project_root(project_root: str = "") -> str:
    """
    Resolve project root from multiple sources (in order of priority):
    1. Explicit argument
    2. CONTEXT_BROKER_PROJECT_ROOT env var
    3. Auto-detection from CWD
    4. Fallback to current working directory
    
    Args:
        project_root: Explicit project root path
        
    Returns:
        Resolved absolute path to project root
    """
    # Priority 1: Explicit argument
    if project_root:
        resolved = Path(project_root).resolve()
        log(f"📁 Using explicit project root: {resolved}")
        return str(resolved)
    
    # Priority 2: Environment variable
    from context_broker.config import DEFAULT_PROJECT_ROOT
    if DEFAULT_PROJECT_ROOT:
        resolved = Path(DEFAULT_PROJECT_ROOT).resolve()
        log(f"📁 Using env project root: {resolved}")
        return str(resolved)
    
    # Priority 3: Auto-detection
    detected = find_project_root()
    if detected:
        log(f"🔍 Auto-detected project root: {detected}")
        return detected
    
    # Priority 4: Fallback to CWD
    cwd = os.getcwd()
    log(f"⚠️ No project markers found, using CWD: {cwd}", "WARN")
    return cwd


def get_project_name(project_root: str | Path) -> str:
    """
    Extract a clean project name from the project root path.
    
    Args:
        project_root: Path to the project root
        
    Returns:
        Project name (directory name)
    """
    return Path(project_root).name or "unknown"
