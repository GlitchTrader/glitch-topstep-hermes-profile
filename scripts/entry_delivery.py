"""Entry delivery revalidation — cognitive band (audit) + executable geometry gate."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from common import append_jsonl, utc_now


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


def _decision_reference_source(market: dict[str, Any]) -> str:
    last = _positive_number(market.get("last"))
    if last is not None:
        return "decision_last"
    bid = _positive_number(market.get("bid"))
    ask = _positive_number(market.get("ask"))
    if bid is not None and ask is not None:
        return "decision_mid"
    if ask is not None:
        return "decision_ask_fallback"
    if bid is not None:
        return "decision_bid_fallback"
    return "decision_unavailable"


def executable_reference_price(market: dict[str, Any], action: str) -> float:
    reference, _source = executable_reference_with_source(market, action)
    return reference


def executable_reference_with_source(
    market: dict[str, Any],
    action: str,
) -> tuple[float, str]:
    bid = _positive_number(market.get("bid"))
    ask = _positive_number(market.get("ask"))
    if action == "ENTER_LONG" and ask is not None:
        return ask, "executable_ask"
    if action == "ENTER_SHORT" and bid is not None:
        return bid, "executable_bid"
    return decision_reference_price(market), _decision_reference_source(market)


def entry_geometry_valid(action: str, stop: float, target: float, reference: float) -> bool:
    if action == "ENTER_LONG":
        return stop < reference < target
    if action == "ENTER_SHORT":
        return target < reference < stop
    return False


def _cognitive_band_breach_direction(
    action: str,
    decision_ref: float,
    low: float,
    high: float,
    *,
    range_valid: bool,
) -> str | None:
    if range_valid:
        return None
    if action == "ENTER_LONG":
        if decision_ref < low:
            return "favorable"
        if decision_ref > high:
            return "adverse"
    elif action == "ENTER_SHORT":
        if decision_ref > high:
            return "favorable"
        if decision_ref < low:
            return "adverse"
    return "unknown"


def _cognitive_band_distance_points(
    decision_ref: float,
    low: float,
    high: float,
    *,
    range_valid: bool,
) -> float:
    if range_valid:
        return 0.0
    if decision_ref < low:
        return low - decision_ref
    if decision_ref > high:
        return decision_ref - high
    return 0.0


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
    executable_ref, reference_source = executable_reference_with_source(market, action)
    range_valid = low <= decision_ref <= high
    geometry_decision = entry_geometry_valid(action, stop, target, decision_ref)
    geometry_executable = entry_geometry_valid(action, stop, target, executable_ref)
    delivery_allowed = geometry_executable
    cognitive_band_breach = not range_valid
    breach_direction = _cognitive_band_breach_direction(
        action,
        decision_ref,
        low,
        high,
        range_valid=range_valid,
    )
    breach_distance_points = _cognitive_band_distance_points(
        decision_ref,
        low,
        high,
        range_valid=range_valid,
    )

    if delivery_allowed:
        status = "accepted"
        reason = "cognitive_band_breach_allowed" if cognitive_band_breach else None
    else:
        status = "superseded"
        reason = "entry_geometry_invalid_at_latest_price"

    return {
        "schema_version": "glitch.topstep.entry_revalidation.v1",
        "status": status,
        "reason": reason,
        "decision_reference_price": decision_ref,
        "executable_reference_price": executable_ref,
        "reference_source": reference_source,
        "entry_price_min": low,
        "entry_price_max": high,
        "range_valid": range_valid,
        "geometry_valid": geometry_decision,
        "geometry_valid_executable": geometry_executable,
        "cognitive_band_breach": cognitive_band_breach,
        "cognitive_band_breach_direction": breach_direction,
        "cognitive_band_distance_points": breach_distance_points,
        "delivery_allowed": delivery_allowed,
    }


def assert_entry_delivery_allowed(intent: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    result = evaluate_entry_revalidation(intent, market)
    if not result["delivery_allowed"]:
        raise ValueError("entry_geometry_invalid_at_latest_price")
    return result


def record_entry_delivery_revalidation(
    state: Path,
    packet_id: str,
    intent: dict[str, Any],
    revalidation: dict[str, Any],
    *,
    rejection_code: str | None = None,
) -> None:
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "entry_delivery_revalidation",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": str(intent.get("intent_id") or ""),
            "action": str(intent.get("action") or ""),
            "decision_reference_price": revalidation.get("decision_reference_price"),
            "executable_reference_price": revalidation.get("executable_reference_price"),
            "reference_source": revalidation.get("reference_source"),
            "entry_price_min": revalidation.get("entry_price_min"),
            "entry_price_max": revalidation.get("entry_price_max"),
            "range_valid": revalidation.get("range_valid"),
            "geometry_valid": revalidation.get("geometry_valid"),
            "geometry_valid_executable": revalidation.get("geometry_valid_executable"),
            "cognitive_band_breach": revalidation.get("cognitive_band_breach"),
            "cognitive_band_breach_direction": revalidation.get("cognitive_band_breach_direction"),
            "cognitive_band_distance_points": revalidation.get("cognitive_band_distance_points"),
            "delivery_allowed": revalidation.get("delivery_allowed"),
            "rejection_code": rejection_code,
            "revalidation_reason": revalidation.get("reason"),
            "revalidation_status": revalidation.get("status"),
        },
    )
