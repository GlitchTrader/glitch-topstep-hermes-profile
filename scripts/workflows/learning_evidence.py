"""Learning evidence budgeting — extracted from run-topstep-learning (audit W3/C1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import read_optional_json

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
