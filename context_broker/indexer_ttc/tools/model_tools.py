"""
Model and tokenizer lifecycle helpers.
"""

import tiktoken
import torch
from sentence_transformers import SentenceTransformer

from context_broker.config import EMBEDDING_MODEL, ENCODING_MODEL, MODEL_DEVICE, MODEL_LOCAL_ONLY, WORKER_CORES
from context_broker.indexer_ttc.tools import state
from context_broker.utils import log


def _create_model(*, local_files_only: bool) -> SentenceTransformer:
    """Create the configured embedding model with the requested cache policy."""
    return SentenceTransformer(
        EMBEDDING_MODEL,
        device=MODEL_DEVICE,
        local_files_only=local_files_only,
    )


def get_model() -> SentenceTransformer:
    """Get or create shared sentence transformer model."""
    if state.SHARED_MODEL is None:
        log(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        torch.set_num_threads(WORKER_CORES)
        try:
            torch.set_num_interop_threads(WORKER_CORES)
        except Exception:
            pass
        if MODEL_LOCAL_ONLY:
            try:
                state.SHARED_MODEL = _create_model(local_files_only=True)
            except Exception:
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
    if state.ENCODER is None:
        state.ENCODER = tiktoken.get_encoding(ENCODING_MODEL)
    return state.ENCODER
