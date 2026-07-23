# Automatic Embedding Model Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically download the configured embedding model on first use, with an exact-model
notification, even when Context Broker is configured for local-only operation.

**Architecture:** Keep `get_model()` as the shared lifecycle entry point. Online mode delegates to
Sentence Transformers with downloads allowed, while local-only mode probes the cache first and
performs one notified online bootstrap retry on a cache miss. Cache-only policy stays scoped to the
model constructor instead of mutating process-wide Hugging Face offline variables.

**Tech Stack:** Python 3.13, sentence-transformers, PyTorch, pytest, uv

## Global Constraints

- Use `log()` for all user-visible model status; never write to MCP stdout.
- Include the exact `CONTEXT_BROKER_EMBEDDING_MODEL` value in bootstrap and failure messages.
- Preserve an explicitly supplied `HF_HUB_OFFLINE` or `TRANSFORMERS_OFFLINE` environment setting.
- Keep the change surgical and within the existing TTC model/config boundaries.
- Run Python and tests through `uv`.

---

### Task 1: Model-loader regression tests and implementation

**Files:**
- Create: `tests/test_model_tools.py`
- Modify: `context_broker/config.py:41-52`
- Modify: `context_broker/indexer_ttc/tools/model_tools.py:14-36`

**Interfaces:**
- Consumes: `model_tools.get_model() -> SentenceTransformer`,
  `state.SHARED_MODEL: Optional[SentenceTransformer]`, and `utils.log(message, level)`.
- Produces: cache-first local-only bootstrap and online first-use notification without changing
  the public `get_model()` signature.

- [ ] **Step 1: Write failing tests for online and cached local-only loads**

```python
"""Regression tests for embedding-model bootstrap behavior."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from context_broker.indexer_ttc.tools import model_tools, state


@pytest.fixture(autouse=True)
def reset_shared_model() -> Iterator[None]:
    state.SHARED_MODEL = None
    yield
    state.SHARED_MODEL = None


def _disable_torch_thread_changes(monkeypatch: Any) -> None:
    monkeypatch.setattr(model_tools.torch, "set_num_threads", lambda _count: None)
    monkeypatch.setattr(model_tools.torch, "set_num_interop_threads", lambda _count: None)


def test_online_mode_names_model_and_allows_automatic_download(
    monkeypatch: Any, capsys: Any
) -> None:
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
        "Embedding model 'org/specific-model' will be downloaded automatically if it is not cached."
        in capsys.readouterr().err
    )


def test_local_only_mode_uses_cached_model_without_download(
    monkeypatch: Any, capsys: Any
) -> None:
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
```

- [ ] **Step 2: Run the two tests and verify online notification fails**

Run:

```bash
uv run pytest tests/test_model_tools.py::test_online_mode_names_model_and_allows_automatic_download \
  tests/test_model_tools.py::test_local_only_mode_uses_cached_model_without_download -v
```

Expected: the online test fails because current code only logs `Loading embedding model`, while the
cached local-only test passes.

- [ ] **Step 3: Add failing cache-miss bootstrap and download-failure tests**

```python
def test_local_only_cache_miss_notifies_and_downloads_exact_model(
    monkeypatch: Any, capsys: Any
) -> None:
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
    monkeypatch: Any
) -> None:
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
```

- [ ] **Step 4: Run the cache-miss tests and verify they fail for the missing fallback**

Run:

```bash
uv run pytest \
  tests/test_model_tools.py::test_local_only_cache_miss_notifies_and_downloads_exact_model \
  tests/test_model_tools.py::test_local_only_download_failure_names_model_and_chains_cause -v
```

Expected: both fail because current local-only behavior raises immediately after the cache miss.

- [ ] **Step 5: Implement the minimal model bootstrap**

Change `context_broker/config.py` so local-only is opt-in and no longer mutates upstream offline
flags:

```python
MODEL_LOCAL_ONLY: bool = os.environ.get("CONTEXT_BROKER_LOCAL_ONLY", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
"""Prefer cache-only model loading, with one automatic bootstrap download on a cache miss."""
```

Replace the model construction branch in `get_model()` with:

```python
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
```

Add this private helper above `get_model()`:

```python
def _create_model(*, local_files_only: bool) -> SentenceTransformer:
    """Create the configured embedding model with the requested cache policy."""
    return SentenceTransformer(
        EMBEDDING_MODEL,
        device=MODEL_DEVICE,
        local_files_only=local_files_only,
    )
```

- [ ] **Step 6: Run the focused model tests**

Run:

```bash
uv run pytest tests/test_model_tools.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Commit the tested loader behavior**

```bash
git add tests/test_model_tools.py context_broker/config.py \
  context_broker/indexer_ttc/tools/model_tools.py
git commit -m "fix: bootstrap missing embedding models"
```

---

### Task 2: User-facing documentation and repository verification

**Files:**
- Modify: `README.md:17,35-38,381-383`
- Modify: `Usage.md:71`
- Modify: `context-broker.py:31`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the model bootstrap behavior delivered by Task 1.
- Produces: accurate first-run configuration guidance and documented release history.

- [ ] **Step 1: Update configuration documentation**

Document these exact rules in README and Usage:

```markdown
- Embedding models download automatically on first use and are cached by Sentence Transformers.
- `CONTEXT_BROKER_LOCAL_ONLY=1` tries the local cache first. If the configured model is missing,
  Context Broker names it in the MCP log and performs a one-time automatic bootstrap download.
- Explicit `HF_HUB_OFFLINE=1` or `TRANSFORMERS_OFFLINE=1` settings still disable that download.
```

Change the documented `CONTEXT_BROKER_LOCAL_ONLY` default from `1` to `0`, and change the
`context-broker.py` environment-variable comment to match the bootstrap behavior.

- [ ] **Step 2: Run formatting and focused tests**

Run:

```bash
uv run ruff check context_broker/config.py \
  context_broker/indexer_ttc/tools/model_tools.py tests/test_model_tools.py
uv run pytest tests/test_model_tools.py -v
```

Expected: ruff exits `0`; model tests report `4 passed`.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass with exit status `0`.

- [ ] **Step 4: Commit documentation and generate changelog history**

Commit the documentation:

```bash
git add README.md Usage.md context-broker.py
git commit -m "docs: explain embedding model bootstrap"
```

Then run `ensure_changelog_tool`, `validate_changelog_tool`, and
`get_changelog_stats_tool`. Stage only `CHANGELOG.md` and commit:

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog"
```

- [ ] **Step 5: Verify the final committed state**

Run:

```bash
git status --short
uv run pytest
```

Expected: only the pre-existing `.claude/` and `.hermes/` untracked directories remain; all tests
pass with exit status `0`.
