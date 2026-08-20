"""Decision journal — single indexed writer over decisions JSONL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from state_store import ProfileStateStore


class DecisionJournal:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store = ProfileStateStore(root)

    def close(self) -> None:
        self.store.close()

    def bootstrap(self, jsonl_path: Path | None = None) -> None:
        path = jsonl_path or self.root / "decisions.jsonl"
        self.store.bootstrap_decisions(path)

    def append(self, row: dict[str, Any], *, jsonl_path: Path | None = None) -> None:
        path = jsonl_path or self.root / "decisions.jsonl"
        self.store.append_decision(row, jsonl_path=path)

    def tail(self, limit: int) -> list[dict[str, Any]]:
        return self.store.tail_decisions(limit)
