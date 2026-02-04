"""
Indexer Module

Handles file indexing, embedding generation, and semantic search.
Uses sentence transformers for embedding generation and cosine similarity for search.
"""

import glob
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import tiktoken
import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from context_broker.config import (
    SUPPORTED_EXTENSIONS, DEFAULT_IGNORE_DIRS, EMBEDDING_MODEL, 
    ENCODING_MODEL, BATCH_SIZE, TOTAL_CORES
)
from context_broker.project import load_ignore_patterns, should_ignore, get_project_name
from context_broker.utils import log, log_ascii_table, count_tokens, get_cache_path

# =============================================================================
# GLOBAL STATE
# =============================================================================

# In-memory indexes: project_root -> index_data
_INDEXES: dict[str, dict[str, Any]] = {}

# Query cache: project_root -> {query_hash -> cache_entry}
_QUERY_CACHE: dict[str, dict[str, Any]] = {}

# Shared model instance (lazy-loaded)
_shared_model: Optional[SentenceTransformer] = None
_encoder: Optional[tiktoken.Encoding] = None


def _get_model() -> SentenceTransformer:
    """Get or create the shared sentence transformer model."""
    global _shared_model
    if _shared_model is None:
        log(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        torch.set_num_threads(TOTAL_CORES)
        _shared_model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _shared_model


def _get_encoder() -> tiktoken.Encoding:
    """Get or create the shared tokenizer."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(ENCODING_MODEL)
    return _encoder


def _generate_cache_key(query: str, top_k: int) -> str:
    """Generate a cache key from query and parameters."""
    key_str = f"{query}:{top_k}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def _load_query_cache(project_root: str) -> dict[str, Any]:
    """Load query cache from disk."""
    global _QUERY_CACHE
    
    if project_root in _QUERY_CACHE:
        return _QUERY_CACHE[project_root]
    
    cache_path = get_cache_path(project_root)
    if not cache_path.exists():
        _QUERY_CACHE[project_root] = {}
        return {}
    
    try:
        with open(cache_path, "r") as f:
            _QUERY_CACHE[project_root] = json.load(f)
            log(f"📦 Loaded cache with {len(_QUERY_CACHE[project_root])} entries")
            return _QUERY_CACHE[project_root]
    except Exception as e:
        log(f"⚠️ Cache load failed: {e}", "WARN")
        _QUERY_CACHE[project_root] = {}
        return {}


def _save_query_cache(project_root: str) -> None:
    """Persist query cache to disk."""
    if project_root not in _QUERY_CACHE:
        return
    
    cache_path = get_cache_path(project_root)
    try:
        with open(cache_path, "w") as f:
            json.dump(_QUERY_CACHE[project_root], f, indent=2)
        log(f"💾 Saved cache with {len(_QUERY_CACHE[project_root])} entries")
    except Exception as e:
        log(f"⚠️ Cache save failed: {e}", "WARN")


def _get_file_mtimes(paths: list[str]) -> dict[str, float]:
    """Get modification times for a list of files."""
    mtimes = {}
    for path in paths:
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            mtimes[path] = 0
    return mtimes


def _is_cache_valid(cache_entry: dict[str, Any], current_mtimes: dict[str, float]) -> bool:
    """Check if cached result is still valid by comparing file mtimes."""
    cached_mtimes = cache_entry.get("file_mtimes", {})
    
    for path, cached_mtime in cached_mtimes.items():
        current_mtime = current_mtimes.get(path, 0)
        if current_mtime != cached_mtime:
            return False
    
    return True


def _read_file_content(filepath: str, max_chars: int = 3000) -> Optional[str]:
    """
    Read file content safely with encoding handling.
    
    Args:
        filepath: Path to the file
        max_chars: Maximum characters to read
        
    Returns:
        File content or None if reading fails
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except Exception:
        return None


def get_index_for_project(root_path: str) -> Optional[dict[str, Any]]:
    """
    Get or create the search index for a project.
    
    This function:
    1. Scans the project for supported files
    2. Respects .gitignore and .dockerignore patterns
    3. Generates embeddings for each file
    4. Caches the index in memory
    
    Args:
        root_path: Path to the project root
        
    Returns:
        Index data dictionary or None if no files found
    """
    global _INDEXES
    
    root_path = os.path.abspath(root_path)
    
    # Return cached index if available
    if root_path in _INDEXES:
        return _INDEXES[root_path]
    
    log(f"⚡ Indexing new project: {root_path}")
    
    model = _get_model()
    encoder = _get_encoder()
    
    # Load ignore patterns
    ignore_patterns = load_ignore_patterns(root_path)
    
    # Scan for files
    documents: list[str] = []
    paths: list[str] = []
    total_project_tokens = 0
    ignored_count = 0
    
    for ext in SUPPORTED_EXTENSIONS:
        pattern = os.path.join(root_path, "**", ext)
        for file_path in glob.glob(pattern, recursive=True):
            rel_path = os.path.relpath(file_path, root_path)
            
            # Check if file should be ignored
            if should_ignore(file_path, rel_path, ignore_patterns, DEFAULT_IGNORE_DIRS):
                ignored_count += 1
                continue
            
            # Read file content
            content = _read_file_content(file_path)
            if content is None:
                continue
            
            file_tokens = count_tokens(content, encoder)
            total_project_tokens += file_tokens
            
            # Create document for embedding
            summary = f"File: {file_path}\nContent: {content[:3000]}"
            documents.append(summary)
            paths.append(file_path)
    
    if ignored_count > 0:
        log(f"🚫 Ignored {ignored_count} files based on ignore patterns")
    
    if not documents:
        log("⚠️ No files found to index", "WARN")
        return None
    
    # Generate embeddings
    log(f"🧠 Embedding {len(documents)} files...")
    embeddings = model.encode(documents, batch_size=BATCH_SIZE, show_progress_bar=False)
    
    # Create index data structure
    index_data = {
        "embeddings": embeddings,
        "paths": paths,
        "model": model,
        "encoder": encoder,
        "total_tokens": total_project_tokens,
        "ignore_patterns": ignore_patterns,
        "project_root": root_path,
    }
    
    _INDEXES[root_path] = index_data
    log(f"✅ Index ready. Total size: {total_project_tokens:,} tokens across {len(documents)} files.")
    
    return index_data


def clear_index(project_root: str) -> bool:
    """
    Clear the in-memory index for a project.
    
    Args:
        project_root: Path to the project root
        
    Returns:
        True if index was cleared, False if it didn't exist
    """
    global _INDEXES
    
    root_path = os.path.abspath(project_root)
    if root_path in _INDEXES:
        del _INDEXES[root_path]
        log(f"🗑️ Cleared index for: {root_path}")
        return True
    return False


def search_codebase(
    query: str, 
    project_root: str, 
    top_k: int = 5
) -> dict[str, Any]:
    """
    Search the codebase using semantic similarity.
    
    This function:
    1. Checks the query cache first
    2. Validates cache against file modification times
    3. Performs semantic search if cache miss or stale
    4. Updates the cache with new results
    
    Args:
        query: Natural language search query
        project_root: Path to the project root
        top_k: Number of results to return
        
    Returns:
        Dictionary with search results and metadata
    """
    if not project_root:
        raise ValueError("project_root is required")
    
    project_root = os.path.abspath(project_root)
    cache_key = _generate_cache_key(query, top_k)
    cache = _load_query_cache(project_root)
    
    # Get or create index
    idx = get_index_for_project(project_root)
    if idx is None:
        raise ValueError(f"No files found in {project_root}")
    
    # Get current file modification times
    current_mtimes = _get_file_mtimes(idx["paths"])
    
    # Check cache
    if cache_key in cache:
        cache_entry = cache[cache_key]
        if _is_cache_valid(cache_entry, current_mtimes):
            log(f"⚡ CACHE HIT for query: {query[:50]}...")
            return _load_cached_results(cache_entry, idx)
        else:
            log(f"🔄 Cache STALE for query: {query[:50]}...")
    
    # Perform search
    log(f"🔍 CACHE MISS for query: {query[:50]}...")
    
    # Encode query and compute similarities
    query_vec = idx["model"].encode([query])
    scores = cosine_similarity(query_vec, idx["embeddings"])[0]
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    # Build results
    results = []
    result_paths = []
    context_tokens = 0
    encoder = idx["encoder"]
    
    for i in top_indices:
        path = idx["paths"][i]
        result_paths.append(path)
        
        content = _read_file_content(path, max_chars=100000)  # Larger limit for results
        if content:
            snippet_tokens = count_tokens(content, encoder)
            context_tokens += snippet_tokens
            results.append({
                "path": path,
                "content": content,
                "similarity_score": float(scores[i]),
                "tokens": snippet_tokens,
            })
    
    # Update cache
    result_mtimes = _get_file_mtimes(result_paths)
    cache[cache_key] = {
        "query": query,
        "top_k": top_k,
        "result_paths": result_paths,
        "file_mtimes": result_mtimes,
    }
    _QUERY_CACHE[project_root] = cache
    _save_query_cache(project_root)
    
    # Calculate statistics
    total_tokens = idx["total_tokens"]
    saved_tokens = total_tokens - context_tokens
    saved_percent = (saved_tokens / total_tokens) * 100 if total_tokens > 0 else 0
    
    log_ascii_table(
        get_project_name(project_root),
        total_tokens,
        context_tokens,
        saved_tokens,
        saved_percent
    )
    
    return {
        "query": query,
        "project": get_project_name(project_root),
        "project_root": project_root,
        "results": results,
        "total_files": len(idx["paths"]),
        "returned_files": len(results),
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "from_cache": False,
    }


def _load_cached_results(cache_entry: dict[str, Any], idx: dict[str, Any]) -> dict[str, Any]:
    """Load results from cache entry, re-reading current file contents."""
    cached_paths = cache_entry.get("result_paths", [])
    results = []
    context_tokens = 0
    encoder = idx["encoder"]
    
    for path in cached_paths:
        content = _read_file_content(path, max_chars=100000)
        if content:
            snippet_tokens = count_tokens(content, encoder)
            context_tokens += snippet_tokens
            results.append({
                "path": path,
                "content": content,
                "similarity_score": 0.0,  # Not available for cached results
                "tokens": snippet_tokens,
            })
    
    total_tokens = idx["total_tokens"]
    saved_tokens = total_tokens - context_tokens
    saved_percent = (saved_tokens / total_tokens) * 100 if total_tokens > 0 else 0
    
    log_ascii_table(
        get_project_name(idx["project_root"]),
        total_tokens,
        context_tokens,
        saved_tokens,
        saved_percent
    )
    
    return {
        "query": cache_entry.get("query", ""),
        "project": get_project_name(idx["project_root"]),
        "project_root": idx["project_root"],
        "results": results,
        "total_files": len(idx["paths"]),
        "returned_files": len(results),
        "total_tokens": total_tokens,
        "context_tokens": context_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "from_cache": True,
    }
