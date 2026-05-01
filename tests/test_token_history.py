"""Tests for token history persistence and graph formatting."""

from pathlib import Path

from context_broker.server_ttc.tasks.token_tasks import (
    _format_token_history_graph,
    _reports_from_runs,
)
from context_broker.storage_ttc.tasks.token_report_tasks import (
    list_token_counter_runs,
    save_token_counter_run,
)


def test_token_counter_run_persists_unique_json(tmp_path: Path) -> None:
    report = {
        "query": "find auth",
        "total_tokens": 1000,
        "context_tokens": 100,
        "saved_tokens": 900,
        "saved_percent": 90.0,
        "embedding_model": "test-embedding",
        "encoding_model": "test-encoding",
    }

    first_path = save_token_counter_run("demo", str(tmp_path), report)
    second_path = save_token_counter_run("demo", str(tmp_path), report)

    assert first_path != second_path
    assert Path(first_path).exists()
    assert Path(second_path).exists()

    runs = list_token_counter_runs("demo", str(tmp_path), limit=10)
    assert len(runs) == 2
    assert runs[0]["report"]["saved_tokens"] == 900


def test_token_history_graph_includes_models_and_json() -> None:
    reports = _reports_from_runs(
        [
            {
                "updated_at": "2026-04-30T20:01:00Z",
                "filename": "token-run-2.json",
                "report": {
                    "context_tokens": 100,
                    "saved_tokens": 900,
                    "saved_percent": 90.0,
                    "embedding_model": "all-MiniLM-L6-v2",
                    "encoding_model": "cl100k_base",
                },
            },
            {
                "updated_at": "2026-04-30T20:00:00Z",
                "filename": "token-run-1.json",
                "report": {
                    "context_tokens": 200,
                    "saved_tokens": 800,
                    "saved_percent": 80.0,
                    "embedding_model": "all-MiniLM-L6-v2",
                    "encoding_model": "cl100k_base",
                },
            },
        ]
    )

    rendered = "\n".join(_format_token_history_graph(reports))

    assert "xychart-beta" in rendered
    assert "Embedding model: all-MiniLM-L6-v2" in rendered
    assert "Token encoding: cl100k_base" in rendered
    assert "80.0" in rendered
    assert "90.0" in rendered
