"""Atomic JSON persistence shared by storage and chat ledgers."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: Any, *, pretty: bool = True) -> None:
    """Replace a JSON file only after serialization and writing succeed."""
    content = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".context-broker-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
