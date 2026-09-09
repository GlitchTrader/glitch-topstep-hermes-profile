"""Explicit Topstep quote-state classification for profile evaluation.

Maps gateway quote_state / issues without fabricating directional outcomes.
Never maps locked/invalid to no_edge.
"""

from __future__ import annotations

from typing import Any

QuoteState = str  # normal | locked | invalid
ExecutionEligibility = str


def _dq(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    dq = payload.get("data_quality")
    return dq if isinstance(dq, dict) else {}


def _issues(dq: dict[str, Any]) -> set[str]:
    raw = dq.get("issues") or []
    return {str(item) for item in raw if item is not None}


def resolve_quote_state(health: dict[str, Any], packet: dict[str, Any]) -> QuoteState:
    """Prefer explicit wire field; fall back to issue codes for older gateways."""
    for source in (packet, health):
        dq = _dq(source)
        explicit = dq.get("quote_state")
        if explicit in ("normal", "locked", "invalid"):
            return str(explicit)
    health_issues = _issues(_dq(health))
    packet_issues = _issues(_dq(packet))
    issues = health_issues | packet_issues
    if "quote_locked" in issues:
        return "locked"
    if "quote_geometry_invalid" in issues or "quote_missing" in issues:
        return "invalid"
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    if market.get("quote_valid") is False:
        return "invalid"
    return "normal"


def resolve_execution_eligibility(health: dict[str, Any], packet: dict[str, Any]) -> ExecutionEligibility:
    for source in (packet, health):
        dq = _dq(source)
        explicit = dq.get("execution_eligibility")
        if explicit in ("eligible", "blocked_locked", "blocked_invalid", "blocked_incomplete"):
            return str(explicit)
    quote_state = resolve_quote_state(health, packet)
    if quote_state == "locked":
        return "blocked_locked"
    if quote_state == "invalid":
        return "blocked_invalid"
    health_dq = _dq(health)
    packet_dq = _dq(packet)
    if health_dq.get("state_complete") is False or packet_dq.get("state_complete") is False:
        return "blocked_incomplete"
    return "eligible"


def resolve_data_completeness(health: dict[str, Any], packet: dict[str, Any]) -> bool:
    for source in (packet, health):
        dq = _dq(source)
        if "data_completeness" in dq:
            return bool(dq.get("data_completeness"))
    # Legacy: treat non-geometry issues as incompleteness.
    geometry = {"quote_locked", "quote_geometry_invalid", "quote_missing"}
    issues = _issues(_dq(health)) | _issues(_dq(packet))
    return len(issues - geometry) == 0 and bool(packet.get("market") is not None)


def classify_evaluation_axes(
    health: dict[str, Any],
    packet: dict[str, Any],
    *,
    execution_authority: bool = False,
) -> dict[str, Any]:
    """Separate operational validity from executable market and directional opportunity."""
    quote_state = resolve_quote_state(health, packet)
    data_completeness = resolve_data_completeness(health, packet)
    execution_eligibility = resolve_execution_eligibility(health, packet)

    operational_cycle_valid = data_completeness and quote_state in ("normal", "locked")
    executable_market_valid = quote_state == "normal" and execution_eligibility == "eligible"
    # Directional opportunity requires executable market; locked never produces a winner.
    directional_opportunity = False

    deferred_reason: str | None = None
    if quote_state == "locked":
        deferred_reason = "no_trade_locked_market"
    elif quote_state == "invalid":
        deferred_reason = "deferred_data_quality"
    elif not executable_market_valid:
        deferred_reason = "deferred_data_quality"

    return {
        "quote_state": quote_state,
        "data_completeness": data_completeness,
        "execution_eligibility": execution_eligibility,
        "operational_cycle_valid": operational_cycle_valid,
        "executable_market_valid": executable_market_valid,
        "directional_opportunity": directional_opportunity,
        "execution_authority": False,
        "deferred_reason": deferred_reason if not executable_market_valid else None,
        "blocks_no_edge": quote_state in ("locked", "invalid"),
    }


def deferred_quote_detail(health: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any] | None:
    """Return deferred detail for locked/invalid quotes only; None otherwise.

    Non-geometry incompleteness stays on the existing state_incomplete path.
    """
    axes = classify_evaluation_axes(health, packet)
    if axes["quote_state"] not in ("locked", "invalid"):
        return None
    health_dq = _dq(health)
    packet_dq = _dq(packet)
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    reason = "no_trade_locked_market" if axes["quote_state"] == "locked" else "quote_geometry_invalid"
    return {
        "reason": reason,
        "quote_state": axes["quote_state"],
        "data_completeness": axes["data_completeness"],
        "execution_eligibility": axes["execution_eligibility"],
        "operational_cycle_valid": axes["operational_cycle_valid"],
        "executable_market_valid": False,
        "directional_opportunity": False,
        "health_state_complete": health_dq.get("state_complete"),
        "packet_state_complete": packet_dq.get("state_complete"),
        "health_issues": sorted(_issues(health_dq)),
        "packet_issues": sorted(_issues(packet_dq)),
        "quote_timestamp": market.get("quote_timestamp"),
        "quote_valid": market.get("quote_valid"),
        "last_invalid": health_dq.get("quote_geometry_last_invalid"),
    }
