"""Explicit Topstep quote-state classification for profile evaluation.

Maps gateway quote_state / issues without fabricating directional outcomes.
Never maps locked/invalid to no_edge.

data_completeness is advisory only — NEVER treat it as execution authorization.
execution_eligibility is the source of truth for new-exposure / risk-increasing mutations.
risk_reduction_eligibility stays open for exit/flatten/protection/recovery on locked/invalid/stale.
"""

from __future__ import annotations

from typing import Any

QuoteState = str  # normal | locked | invalid
ExecutionEligibility = str

# quote_state × action → allowed (mirrors gateway actionAllowedForQuote)
ACTION_MATRIX: dict[str, dict[str, bool]] = {
    "normal": {
        "new_exposure": True,
        "risk_increasing_amendment": True,
        "exit_reduction": True,
        "flatten": True,
        "protective_action": True,
        "recovery": True,
    },
    "locked": {
        "new_exposure": False,
        "risk_increasing_amendment": False,
        "exit_reduction": True,
        "flatten": True,
        "protective_action": True,
        "recovery": True,
    },
    "invalid": {
        "new_exposure": False,
        "risk_increasing_amendment": False,
        "exit_reduction": True,
        "flatten": True,
        "protective_action": True,
        "recovery": True,
    },
    "stale": {
        "new_exposure": False,
        "risk_increasing_amendment": False,
        "exit_reduction": True,
        "flatten": True,
        "protective_action": True,
        "recovery": True,
    },
}


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
    """New-exposure gate only — never authorize from data_completeness alone."""
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


def resolve_risk_reduction_eligibility(health: dict[str, Any], packet: dict[str, Any]) -> str:
    for source in (packet, health):
        dq = _dq(source)
        if dq.get("risk_reduction_eligibility") == "eligible":
            return "eligible"
    # Quote geometry / stale must never close reduction paths.
    return "eligible"


def resolve_data_completeness(health: dict[str, Any], packet: dict[str, Any]) -> bool:
    """Advisory only — consumers must not treat True as execution authorization."""
    for source in (packet, health):
        dq = _dq(source)
        if "data_completeness" in dq:
            return bool(dq.get("data_completeness"))
    geometry = {"quote_locked", "quote_geometry_invalid", "quote_missing"}
    issues = _issues(_dq(health)) | _issues(_dq(packet))
    return len(issues - geometry) == 0 and bool(packet.get("market") is not None)


def action_allowed(action: str, *, quote_state: str, execution_eligibility: str) -> bool:
    if action in ("new_exposure", "risk_increasing_amendment"):
        return execution_eligibility == "eligible"
    if action in ("exit_reduction", "flatten", "protective_action", "recovery"):
        return True
    matrix_key = "stale" if execution_eligibility == "blocked_incomplete" else quote_state
    return bool(ACTION_MATRIX.get(matrix_key, ACTION_MATRIX["invalid"]).get(action, False))


def classify_evaluation_axes(
    health: dict[str, Any],
    packet: dict[str, Any],
    *,
    execution_authority: bool = False,
) -> dict[str, Any]:
    """Separate operational validity from executable market and directional opportunity."""
    del execution_authority  # soak/shadow stay false; parameter reserved for callers
    quote_state = resolve_quote_state(health, packet)
    data_completeness = resolve_data_completeness(health, packet)
    execution_eligibility = resolve_execution_eligibility(health, packet)
    risk_reduction_eligibility = resolve_risk_reduction_eligibility(health, packet)

    # data_completeness alone never authorizes; executable_market requires execution_eligibility.
    operational_cycle_valid = data_completeness and quote_state in ("normal", "locked")
    executable_market_valid = quote_state == "normal" and execution_eligibility == "eligible"
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
        "risk_reduction_eligibility": risk_reduction_eligibility,
        "operational_cycle_valid": operational_cycle_valid,
        "executable_market_valid": executable_market_valid,
        "directional_opportunity": directional_opportunity,
        "execution_authority": False,
        "deferred_reason": deferred_reason if not executable_market_valid else None,
        "blocks_no_edge": quote_state in ("locked", "invalid"),
        "action_matrix": {
            action: action_allowed(
                action,
                quote_state=quote_state,
                execution_eligibility=execution_eligibility,
            )
            for action in (
                "new_exposure",
                "risk_increasing_amendment",
                "exit_reduction",
                "flatten",
                "protective_action",
                "recovery",
            )
        },
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
        "risk_reduction_eligibility": axes["risk_reduction_eligibility"],
        "operational_cycle_valid": axes["operational_cycle_valid"],
        "executable_market_valid": False,
        "directional_opportunity": False,
        "action_matrix": axes["action_matrix"],
        "health_state_complete": health_dq.get("state_complete"),
        "packet_state_complete": packet_dq.get("state_complete"),
        "health_issues": sorted(_issues(health_dq)),
        "packet_issues": sorted(_issues(packet_dq)),
        "quote_timestamp": market.get("quote_timestamp"),
        "quote_valid": market.get("quote_valid"),
        "last_invalid": health_dq.get("quote_geometry_last_invalid"),
    }
