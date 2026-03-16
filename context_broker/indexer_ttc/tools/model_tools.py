"""
Model and tokenizer lifecycle helpers.
"""

import tiktoken
import torch
from sentence_transformers import SentenceTransformer

from context_broker.config import EMBEDDING_MODEL, ENCODING_MODEL, MODEL_LOCAL_ONLY, WORKER_CORES
from context_broker.indexer_ttc.tools import state
from context_broker.utils import log


def get_model() -> SentenceTransformer:
    """Get or create shared sentence transformer model."""
    if state.SHARED_MODEL is None:
        log(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        torch.set_num_threads(WORKER_CORES)
        try:
            torch.set_num_interop_threads(WORKER_CORES)
        except Exception:
            pass
        try:
            state.SHARED_MODEL = SentenceTransformer(
                EMBEDDING_MODEL,
                device="cpu",
                local_files_only=MODEL_LOCAL_ONLY,
            )
        except Exception as e:
            if MODEL_LOCAL_ONLY:
                raise RuntimeError(
                    "Local-only mode is enabled and the embedding model is not available locally. "
                    "Pre-download the model or disable CONTEXT_BROKER_LOCAL_ONLY."
                ) from e
            raise
    return state.SHARED_MODEL


def get_encoder() -> tiktoken.Encoding:
    """Get or create shared tokenizer."""
    if state.ENCODER is None:
        state.ENCODER = tiktoken.get_encoding(ENCODING_MODEL)
    return state.ENCODER
