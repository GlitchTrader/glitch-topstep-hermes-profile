"""Baseline vs challenger comparison with explicit outcome categories."""

from __future__ import annotations

from typing import Any

COMPARISON_CATEGORIES = frozenset({
    "thesis_quality",
    "missing_required_evidence",
    "schema_invalid",
    "timeout",
    "not_comparable",
    "no_edge",
    "directional_delta",
})


def _normalized(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("normalized")
    if isinstance(value, dict):
        return value
    return row


def classify_candidate(normalized: dict[str, Any], gate: dict[str, Any]) -> str:
    state = str(normalized.get("state") or "")
    if state == "timeout":
        return "timeout"
    if state == "invalid":
        return "schema_invalid"
    if state == "missing_required_evidence" or not gate.get("comparable", True):
        return "missing_required_evidence"
    if str(normalized.get("comparability") or "") == "not_comparable":
        return "not_comparable"
    if state == "no_edge":
        return "no_edge"
    if state in {"candidate", "held"}:
        return "thesis_quality"
    if state == "error":
        return "schema_invalid"
    return "not_comparable"


def compare_frame_profiles(
    *,
    frame_id: str,
    candidates: list[dict[str, Any]],
    capacity_gates: list[dict[str, Any]],
    baseline_id: str = "baseline-current",
    challenger_id: str = "structure",
) -> dict[str, Any]:
    by_profile = {str(row.get("profile_id")): row for row in candidates}
    gates_by_profile = {str(row.get("profile_id")): row for row in capacity_gates}
    baseline_row = by_profile.get(baseline_id)
    challenger_row = by_profile.get(challenger_id)
    if baseline_row is None or challenger_row is None:
        raise ValueError("baseline_or_challenger_missing")

    baseline = _normalized(baseline_row)
    challenger = _normalized(challenger_row)
    baseline_gate = gates_by_profile.get(baseline_id, {})
    challenger_gate = gates_by_profile.get(challenger_id, {})

    baseline_category = classify_candidate(baseline, baseline_gate)
    challenger_category = classify_candidate(challenger, challenger_gate)

    comparable_pair = (
        baseline_category == "thesis_quality"
        and challenger_category == "thesis_quality"
        and str(baseline.get("comparability") or "") == "comparable"
        and str(challenger.get("comparability") or "") == "comparable"
    )

    direction_delta = None
    if comparable_pair:
        if baseline.get("direction") != challenger.get("direction"):
            direction_delta = {
                "baseline": baseline.get("direction"),
                "challenger": challenger.get("direction"),
            }

    return {
        "frame_id": frame_id,
        "baseline_profile_id": baseline_id,
        "challenger_profile_id": challenger_id,
        "baseline_category": baseline_category,
        "challenger_category": challenger_category,
        "comparable_pair": comparable_pair,
        "direction_delta": direction_delta,
        "thesis_delta": (
            baseline.get("thesis") != challenger.get("thesis")
            if comparable_pair
            else None
        ),
        "notes": [
            "Categories are mutually tracked; missing_required_evidence is not counted as no_edge.",
            "not_comparable preserves audit direction without thesis-quality comparison.",
        ],
    }
