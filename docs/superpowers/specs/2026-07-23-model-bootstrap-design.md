# Embedding Model Bootstrap Design

## Goal

Make a fresh Context Broker installation usable without manually pre-downloading its
configured Sentence Transformers model. The MCP must name the model before an automatic
download starts, including when `CONTEXT_BROKER_LOCAL_ONLY=1`.

## Behavior

`get_model()` keeps the shared in-memory model lifecycle. In normal online mode, it logs that
the configured model will be downloaded automatically if absent, then lets
`SentenceTransformer` load or download it.

In local-only mode, it first attempts a cache-only load. If that succeeds, no network access is
needed. If the model is absent, it logs a warning containing the exact configured model name and
explaining that a one-time automatic download is starting. It then retries with network access
enabled so Sentence Transformers can download and cache the model.

`CONTEXT_BROKER_LOCAL_ONLY` therefore means "use only the local cache after bootstrap," rather
than "make a fresh installation unusable." Explicit upstream offline settings such as
`HF_HUB_OFFLINE=1` remain authoritative; Context Broker will not silently unset settings supplied
by the user.

## Configuration

The default for `CONTEXT_BROKER_LOCAL_ONLY` changes from enabled to disabled so first-run
installation follows Sentence Transformers' standard automatic-download behavior.

Context Broker stops setting global Hugging Face and Transformers offline environment variables
itself. Cache-only behavior is enforced narrowly through `SentenceTransformer`'s
`local_files_only` argument. This allows the controlled bootstrap retry without changing unrelated
library behavior.

## Error Handling

If the automatic download fails, the raised error identifies the configured model and states that
both the local load and automatic download failed. The original exception remains chained for
diagnostics.

## Tests

Regression tests will verify:

- online mode names the configured model and permits automatic download;
- local-only mode uses the cache without a network retry when the model exists;
- local-only cache miss logs the exact model before retrying online;
- the successful retry becomes the shared model;
- download failure reports the exact model and preserves the underlying exception.

README and usage documentation will describe local-only bootstrap semantics and remove the manual
pre-download requirement from the first-run path.
