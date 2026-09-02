"""Apply capacity-gate overlay without erasing audit direction."""

from __future__ import annotations

from typing import Any

from evaluation_output_adapter import adapt_evaluation_output


def apply_capacity_gate_overlay(
    *,
    fixture: dict[str, Any] | None,
    gate: dict[str, Any],
) -> dict[str, Any]:
    return adapt_evaluation_output(raw=fixture, gate=gate)
