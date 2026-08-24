"""Compact recent lifecycle facts for cycle cognition (NT parity)."""

from __future__ import annotations

from typing import Any

from common import tail_jsonl

LIFECYCLE_EXIT_PHASES = frozenset({
    "exit_fill_observed",
    "position_flat",
    "exit_submitted",
})


def _compact_execution_fact(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: row.get(key)
        for key in ("recorded_utc", "intent_id", "phase", "status", "sequence", "fact_id")
        if row.get(key) is not None
    }
    detail = row.get("detail")
    if isinstance(detail, dict):
        for key in ("realized_pnl_usd", "fill_price", "quantity", "instrument", "code", "message"):
            if detail.get(key) is not None:
                compact[key] = detail[key]
    return compact


def recent_execution_facts_for_cycle(
    state,
    outcomes: list[dict[str, Any]],
    *,
    tail_limit: int = 12,
) -> list[dict[str, Any]]:
    """Surface exit fills until the enriched outcome catches up; always keep a short tail."""
    rows = tail_jsonl(state / "execution-facts.jsonl", max(tail_limit * 4, 48))
    outcome_ids = {
        str(row.get("intent_id") or "")
        for row in outcomes
        if row.get("intent_id")
    }
    retained: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase") or "")
        intent_id = str(row.get("intent_id") or "")
        if phase in LIFECYCLE_EXIT_PHASES and intent_id and intent_id not in outcome_ids:
            compact = _compact_execution_fact(row)
            key = (
                str(compact.get("recorded_utc") or ""),
                intent_id,
                phase,
            )
            if key not in seen:
                retained.append(compact)
                seen.add(key)
    for row in rows[-tail_limit:]:
        if not isinstance(row, dict):
            continue
        compact = _compact_execution_fact(row)
        key = (
            str(compact.get("recorded_utc") or ""),
            str(compact.get("intent_id") or ""),
            str(compact.get("phase") or ""),
        )
        if key not in seen:
            retained.append(compact)
            seen.add(key)
    retained.sort(key=lambda row: str(row.get("recorded_utc") or ""))
    return retained[-tail_limit * 2 :]
