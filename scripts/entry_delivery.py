"""Entry band revalidation — NT parity for decision reference and favorable supersession."""

from __future__ import annotations

import math
from typing import Any


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def decision_reference_price(market: dict[str, Any]) -> float:
    last = _positive_number(market.get("last"))
    if last is not None:
        return last
    bid = _positive_number(market.get("bid"))
    ask = _positive_number(market.get("ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    if ask is not None:
        return ask
    if bid is not None:
        return bid
    raise ValueError("delivery_reference_price")


def executable_reference_price(market: dict[str, Any], action: str) -> float:
    bid = _positive_number(market.get("bid"))
    ask = _positive_number(market.get("ask"))
    if action == "ENTER_LONG":
        if ask is not None:
            return ask
    elif action == "ENTER_SHORT":
        if bid is not None:
            return bid
    return decision_reference_price(market)


def entry_geometry_valid(action: str, stop: float, target: float, reference: float) -> bool:
    if action == "ENTER_LONG":
        return stop < reference < target
    if action == "ENTER_SHORT":
        return target < reference < stop
    return False


def evaluate_entry_revalidation(
    intent: dict[str, Any],
    market: dict[str, Any],
) -> dict[str, Any]:
    action = str(intent.get("action") or "")
    stop = _positive_number(intent.get("stop_loss"))
    target = _positive_number(intent.get("take_profit_1"))
    low = _positive_number(intent.get("entry_price_min"))
    high = _positive_number(intent.get("entry_price_max"))
    if low is None or high is None or stop is None or target is None or low > high:
        raise ValueError("entry_price_range_invalid")

    decision_ref = decision_reference_price(market)
    executable_ref = executable_reference_price(market, action)
    range_valid = low <= decision_ref <= high
    geometry_decision = entry_geometry_valid(action, stop, target, decision_ref)
    geometry_executable = entry_geometry_valid(action, stop, target, executable_ref)
    favorable = (
        not range_valid
        and geometry_executable
        and (
            (action == "ENTER_LONG" and decision_ref < low)
            or (action == "ENTER_SHORT" and decision_ref > high)
        )
    )
    accepted = range_valid and geometry_decision
    status = "accepted" if accepted else "superseded"
    reason = None
    if not accepted:
        if not geometry_executable:
            reason = "entry_geometry_invalid_at_latest_price"
        elif not range_valid and not favorable:
            reason = "latest_price_outside_entry_range"
        elif favorable:
            reason = "favorable_supersession"
    return {
        "schema_version": "glitch.topstep.entry_revalidation.v1",
        "status": status,
        "reason": reason,
        "decision_reference_price": decision_ref,
        "executable_reference_price": executable_ref,
        "entry_price_min": low,
        "entry_price_max": high,
        "geometry_valid": geometry_decision,
        "geometry_valid_executable": geometry_executable,
        "favorable_supersession": favorable,
        "delivery_allowed": accepted or favorable,
    }


def assert_entry_delivery_allowed(intent: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    result = evaluate_entry_revalidation(intent, market)
    if not result["delivery_allowed"]:
        raise ValueError("entry_range_superseded")
    return result
