"""
Model and tokenizer lifecycle helpers.
"""

from __future__ import annotations

import importlib
from typing import Any

import tiktoken

from context_broker.config import (
    EMBEDDING_MODEL,
    ENCODING_MODEL,
    MODEL_DEVICE,
    MODEL_LOCAL_ONLY,
    WORKER_CORES,
)
from context_broker.indexer_ttc.tools import state
from context_broker.utils import log


def __getattr__(name: str) -> Any:
    """Load ML libraries only when semantic inference is first requested."""
    if name in globals():
        return globals()[name]
    if name == "torch":
        value = importlib.import_module("torch")
    elif name == "SentenceTransformer":
        value = importlib.import_module("sentence_transformers").SentenceTransformer
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value


def _create_model(*, local_files_only: bool) -> Any:
    """Create the configured embedding model with the requested cache policy."""
    return __getattr__("SentenceTransformer")(
        EMBEDDING_MODEL,
        device=MODEL_DEVICE,
        local_files_only=local_files_only,
    )


def get_model() -> Any:
    """Initialize one model even when multiple sessions arrive concurrently."""
    with state.MODEL_LOCK:
        return _load_model()


def _load_model() -> Any:
    """Load the model while holding the shared initialization lock."""
    if state.SHARED_MODEL is None:
        log(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        __getattr__("torch").set_num_threads(WORKER_CORES)
        try:
            __getattr__("torch").set_num_interop_threads(WORKER_CORES)
        except Exception:
            pass
        if MODEL_LOCAL_ONLY:
            try:
                state.SHARED_MODEL = _create_model(local_files_only=True)
            except OSError:
                log(
                    f"Embedding model '{EMBEDDING_MODEL}' is not available locally. "
                    "Downloading it automatically now; this is a one-time download.",
                    "WARN",
                )
                try:
                    state.SHARED_MODEL = _create_model(local_files_only=False)
                except Exception as download_error:
                    raise RuntimeError(
                        f"Embedding model '{EMBEDDING_MODEL}' is not available locally "
                        "and the automatic download failed."
                    ) from download_error
        else:
            log(
                f"Embedding model '{EMBEDDING_MODEL}' will be downloaded automatically "
                "if it is not cached."
            )
            state.SHARED_MODEL = _create_model(local_files_only=False)
    return state.SHARED_MODEL


def get_encoder() -> tiktoken.Encoding:
    """Get or create shared tokenizer."""
    with state.MODEL_LOCK:
        if state.ENCODER is None:
            state.ENCODER = tiktoken.get_encoding(ENCODING_MODEL)
        return state.ENCODER
