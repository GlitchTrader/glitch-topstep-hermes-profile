"""Corrected evaluation strata v2 — daily_capture_locked → operationally_blocked."""

from __future__ import annotations

from typing import Any

CORRECTED_STRATA = frozenset(
    {
        "valid_abstention",
        "operationally_blocked",
        "data_degradation",
        "insufficient_capacity",
        "candidate_unilateral",
        "comparable_thesis_pair",
    }
)

RULE_CHAIN = [
    "daily_capture_locked → operationally_blocked",
    "not abstention_valid",
    "not thesis_quality",
]


def daily_capture_locked(packet: dict[str, Any] | None) -> bool:
    if not isinstance(packet, dict):
        return False
    execution = packet.get("execution")
    if isinstance(execution, dict) and execution.get("daily_capture_locked") is True:
        return True
    policy = packet.get("policy")
    if isinstance(policy, dict) and policy.get("daily_capture_locked") is True:
        return True
    dc = packet.get("daily_capture")
    if isinstance(dc, dict) and dc.get("reached") is True and dc.get("new_exposure_lock_configured") is True:
        return True
    return False


def capture_has_degradation(
    *,
    gateway_degraded: bool | None = None,
    bar_issues: list[str] | None = None,
) -> bool:
    if gateway_degraded:
        return True
    return bool(bar_issues)


def diagnostically_evaluable(*, classification_v2: str, capture_degraded: bool) -> bool:
    if classification_v2 in {"operationally_blocked", "insufficient_capacity", "data_degradation"}:
        return False
    if capture_degraded:
        return False
    return classification_v2 in {"valid_abstention", "candidate_unilateral", "comparable_thesis_pair"}


def classify_replay_row(
    *,
    packet: dict[str, Any] | None,
    baseline_category: str | None,
    challenger_category: str | None,
    comparable_pair: bool,
    capacity_comparable: bool | None,
    capture_degraded: bool = False,
) -> str:
    if comparable_pair and baseline_category == "thesis_quality" and challenger_category == "thesis_quality":
        return "comparable_thesis_pair"
    if daily_capture_locked(packet):
        return "operationally_blocked"
    if capture_degraded:
        return "data_degradation"
    if capacity_comparable is False:
        return "insufficient_capacity"
    if baseline_category == "no_edge" and challenger_category == "no_edge":
        return "valid_abstention"
    if baseline_category in {"candidate", "thesis_quality", "held"} or challenger_category in {
        "candidate",
        "thesis_quality",
        "held",
    }:
        return "candidate_unilateral"
    return "valid_abstention"


def classify_production_decision(
    *,
    packet: dict[str, Any] | None,
    action: str | None,
    capture_degraded: bool = False,
) -> str:
    if daily_capture_locked(packet):
        return "operationally_blocked"
    if capture_degraded:
        return "data_degradation"
    if str(action or "").upper() == "NOTHING":
        return "valid_abstention"
    return "candidate_unilateral"


def classify_frame_product(
    *,
    packet: dict[str, Any] | None,
    action: str | None,
    capacity_gate_pass: bool,
    gateway_state_complete_at_decision: bool | None,
    bar_complete: bool,
) -> str:
    """Product-facing frame class (health-correlated). Lock wins over abstention."""
    if daily_capture_locked(packet):
        return "operationally_blocked"
    if not capacity_gate_pass:
        return "insufficient_capacity"
    if gateway_state_complete_at_decision is False or not bar_complete:
        return "data_degradation"
    if str(action or "").upper() == "NOTHING":
        return "valid_abstention"
    if str(action or "").upper() in {"ENTER_LONG", "ENTER_SHORT"}:
        return "valid_opportunity"
    return "valid_abstention"


def count_strata(rows: list[dict[str, Any]], key: str = "classification_v2") -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        bucket = str(row.get(key) or "unknown")
        out[bucket] = out.get(bucket, 0) + 1
    return dict(sorted(out.items()))
