"""Cycle cognition context assembly — entry scripts stay thin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import tail_jsonl
from parity import compact_cycle_ledger_context, learning_context
from state_store import ProfileStateStore


def recent_cycle_context(root: Path, *, tail_limit: int = 4) -> dict[str, Any]:
    supervisor = root / "supervisor"
    context = learning_context(supervisor)
    store = ProfileStateStore(root)
    try:
        store.bootstrap_decisions(root / "decisions.jsonl")
        decisions = store.tail_decisions(tail_limit)
    finally:
        store.close()
    context.update(
        compact_cycle_ledger_context(
            decisions=decisions,
            receipts=tail_jsonl(root / "receipts.jsonl", tail_limit),
            outcomes=tail_jsonl(root / "outcomes.jsonl", tail_limit),
        )
    )
    return context
