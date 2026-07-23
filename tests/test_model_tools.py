"""Regression tests for embedding-model bootstrap behavior."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import runpy
from typing import Any

import pytest

from context_broker import config
from context_broker.indexer_ttc.tools import model_tools, state


@pytest.fixture(autouse=True)
def reset_shared_model() -> Iterator[None]:
    """Keep the process-wide model singleton isolated between tests."""
    state.SHARED_MODEL = None
    yield
    state.SHARED_MODEL = None


def _disable_torch_thread_changes(monkeypatch: Any) -> None:
    """Avoid changing process-wide PyTorch thread settings in unit tests."""
    monkeypatch.setattr(model_tools.torch, "set_num_threads", lambda _count: None)
    monkeypatch.setattr(model_tools.torch, "set_num_interop_threads", lambda _count: None)


def test_local_only_defaults_to_disabled_without_forcing_upstream_offline_flags(
    monkeypatch: Any,
) -> None:
    """Fresh installations should permit Sentence Transformers to bootstrap its model."""
    monkeypatch.delenv("CONTEXT_BROKER_LOCAL_ONLY", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    loaded_config = runpy.run_path(str(Path(config.__file__)))

    assert loaded_config["MODEL_LOCAL_ONLY"] is False
    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ


def test_online_mode_names_model_and_allows_automatic_download(
    monkeypatch: Any, capsys: Any
) -> None:
    """Online mode should explain first-use download behavior for the exact model."""
    _disable_torch_thread_changes(monkeypatch)
    model = object()
    calls: list[tuple[str, str, bool]] = []

    def fake_sentence_transformer(
        name: str, *, device: str, local_files_only: bool
    ) -> object:
        calls.append((name, device, local_files_only))
        return model

    monkeypatch.setattr(model_tools, "MODEL_LOCAL_ONLY", False)
    monkeypatch.setattr(model_tools, "EMBEDDING_MODEL", "org/specific-model")
    monkeypatch.setattr(model_tools, "SentenceTransformer", fake_sentence_transformer)

    assert model_tools.get_model() is model
    assert calls == [("org/specific-model", model_tools.MODEL_DEVICE, False)]
    assert (
        "Embedding model 'org/specific-model' will be downloaded automatically "
        "if it is not cached."
        in capsys.readouterr().err
    )


def test_local_only_mode_uses_cached_model_without_download(
    monkeypatch: Any, capsys: Any
) -> None:
    """Local-only mode should stay offline when the configured model is cached."""
    _disable_torch_thread_changes(monkeypatch)
    model = object()
    calls: list[bool] = []

    def fake_sentence_transformer(
        _name: str, *, device: str, local_files_only: bool
    ) -> object:
        calls.append(local_files_only)
        return model

    monkeypatch.setattr(model_tools, "MODEL_LOCAL_ONLY", True)
    monkeypatch.setattr(model_tools, "SentenceTransformer", fake_sentence_transformer)

    assert model_tools.get_model() is model
    assert calls == [True]
    assert "Downloading it automatically" not in capsys.readouterr().err


def test_local_only_cache_miss_notifies_and_downloads_exact_model(
    monkeypatch: Any, capsys: Any
) -> None:
    """A missing local model should trigger one clearly announced bootstrap download."""
    _disable_torch_thread_changes(monkeypatch)
    downloaded_model = object()
    calls: list[bool] = []

    def fake_sentence_transformer(
        _name: str, *, device: str, local_files_only: bool
    ) -> object:
        calls.append(local_files_only)
        if local_files_only:
            raise OSError("model is not cached")
        return downloaded_model

    monkeypatch.setattr(model_tools, "MODEL_LOCAL_ONLY", True)
    monkeypatch.setattr(model_tools, "EMBEDDING_MODEL", "org/bootstrap-model")
    monkeypatch.setattr(model_tools, "SentenceTransformer", fake_sentence_transformer)

    assert model_tools.get_model() is downloaded_model
    assert calls == [True, False]
    assert (
        "Embedding model 'org/bootstrap-model' is not available locally. "
        "Downloading it automatically now; this is a one-time download."
        in capsys.readouterr().err
    )


def test_local_only_download_failure_names_model_and_chains_cause(
    monkeypatch: Any,
) -> None:
    """A failed bootstrap should identify the model and preserve the network error."""
    _disable_torch_thread_changes(monkeypatch)
    download_error = ConnectionError("network unavailable")

    def fake_sentence_transformer(
        _name: str, *, device: str, local_files_only: bool
    ) -> object:
        if local_files_only:
            raise OSError("model is not cached")
        raise download_error

    monkeypatch.setattr(model_tools, "MODEL_LOCAL_ONLY", True)
    monkeypatch.setattr(model_tools, "EMBEDDING_MODEL", "org/unavailable-model")
    monkeypatch.setattr(model_tools, "SentenceTransformer", fake_sentence_transformer)

    with pytest.raises(
        RuntimeError,
        match=(
            "Embedding model 'org/unavailable-model' is not available locally "
            "and the automatic download failed"
        ),
    ) as exc_info:
        model_tools.get_model()

    assert exc_info.value.__cause__ is download_error
