"""Cognition prompt context assembly — keeps run-topstep-cycle thin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import tail_jsonl
from parity import compact_cycle_ledger_context, learning_context
from workflows.decision_journal import DecisionJournal


def recent_cycle_context(root: Path, *, tail_limit: int = 4) -> dict[str, Any]:
    supervisor = root / "supervisor"
    context = learning_context(supervisor)
    journal = DecisionJournal(root)
    try:
        journal.bootstrap(root / "decisions.jsonl")
        decisions = journal.tail(tail_limit)
    finally:
        journal.close()
    context.update(
        compact_cycle_ledger_context(
            decisions=decisions,
            receipts=tail_jsonl(root / "receipts.jsonl", tail_limit),
            outcomes=tail_jsonl(root / "outcomes.jsonl", tail_limit),
        )
    )
    return context
