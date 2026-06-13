"""Atomic JSON/JSONL file helpers for the durable filesystem corpus."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, payload: Any) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def dump_jsonl_line(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    write_text_atomic(path, "".join(dump_jsonl_line(row) + "\n" for row in rows))


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(dump_jsonl_line(row) + "\n")


def upsert_jsonl(path: Path, rows: list[dict[str, Any]], key: str) -> int:
    """Merge rows into a JSONL file by key, replacing existing rows in place. Returns the number of new rows.

    Ordering contract: existing rows keep their file order; new keys are appended (dict insertion order).
    """
    existing = read_jsonl(path)
    by_key = {row[key]: row for row in existing}
    inserted = 0
    for row in rows:
        if row[key] not in by_key:
            inserted += 1
        by_key[row[key]] = row
    merged = list(by_key.values())
    write_jsonl_atomic(path, merged)
    return inserted
