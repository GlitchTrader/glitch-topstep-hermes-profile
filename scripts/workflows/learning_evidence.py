"""Learning evidence budgeting — extracted from run-topstep-learning (audit W3/C1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import read_optional_json
from parity import debrief_evidence, debrief_prompt_evidence
from workflows.learning_journal import stable_id

MAX_PROMPT_CHARS = 320_000
LEARNING_REPAIR_PROMPT_RESERVE_CHARS = 2_000


def bounded_learning_rows(
    rows: list[dict[str, Any]], max_rows: int, max_chars: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for row in reversed(rows):
        row_chars = len(json.dumps(row, separators=(",", ":"), ensure_ascii=False))
        if len(selected) >= max_rows or used_chars + row_chars > max_chars:
            break
        selected.append(row)
        used_chars += row_chars
    return list(reversed(selected))


def prompt_fits_budget(prompt: str, *, reserve_chars: int = LEARNING_REPAIR_PROMPT_RESERVE_CHARS) -> bool:
    return len(prompt) <= MAX_PROMPT_CHARS - reserve_chars


def overlay_context(supervisor: Path) -> dict[str, Any]:
    return {
        "current_plan": read_optional_json(supervisor / "current-plan.json"),
        "current_guidance": read_optional_json(supervisor / "current-guidance.json"),
        "active_cognitive_overlay": read_optional_json(supervisor / "active-cognitive-overlay.json"),
    }


def outcome_is_reconciled_for_learning(row: dict[str, Any]) -> bool:
    if row.get("learning_eligible") is not True:
        return False
    fills = row.get("fills")
    has_fills = isinstance(fills, list) and len(fills) >= 1
    chronology = row.get("path_chronology")
    has_chronology = isinstance(chronology, dict) and chronology.get("schema_version")
    protection = str(row.get("protection_status") or "").lower()
    if protection in {"pending", "unknown", "failed"}:
        return False
    return bool(has_fills or has_chronology)


def fit_debrief_evidence(
    state_root: Path,
    outcomes: list[dict[str, Any]],
    supervisor: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the oldest complete debrief slice inside the model and repair budgets."""
    from workflows.learning_loops import output_template, prompt_for

    batch = list(outcomes)
    evidence = debrief_evidence(state_root, batch)
    while batch:
        ids = [stable_id("episode", str(row["outcome_id"])) for row in batch]
        prompt = prompt_for(
            "debrief",
            debrief_prompt_evidence(evidence),
            output_template("debrief", ids),
            overlay_context(supervisor),
        )
        if prompt_fits_budget(prompt):
            return batch, evidence
        batch.pop()
        evidence.pop()
    raise ValueError("learning_prompt_too_large:debrief:single_outcome")
