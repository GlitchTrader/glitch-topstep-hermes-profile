"""Evaluation-only entry candidate geometry (not gateway execution authority)."""

from __future__ import annotations

import math
from typing import Any


def tick_size_from_envelope(envelope: dict[str, Any]) -> float:
    contract = envelope.get("contract")
    if isinstance(contract, dict):
        tick = contract.get("tick_size")
        if isinstance(tick, (int, float)) and math.isfinite(float(tick)) and float(tick) > 0:
            return float(tick)
    packet = envelope.get("packet")
    if isinstance(packet, dict):
        nested = packet.get("contract")
        if isinstance(nested, dict):
            tick = nested.get("tick_size")
            if isinstance(tick, (int, float)) and math.isfinite(float(tick)) and float(tick) > 0:
                return float(tick)
    return 0.25


def reference_price_from_envelope(envelope: dict[str, Any]) -> float:
    packet = envelope.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("envelope_packet_missing")
    market = packet.get("market")
    if not isinstance(market, dict):
        raise ValueError("envelope_market_missing")
    last = market.get("last")
    if isinstance(last, (int, float)) and math.isfinite(float(last)) and float(last) > 0:
        return float(last)
    bid = market.get("bid")
    ask = market.get("ask")
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        return (float(bid) + float(ask)) / 2.0
    raise ValueError("envelope_reference_price_missing")


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def entry_reference(entry: float | None, entry_range: dict[str, Any] | None) -> float | None:
    if entry is not None:
        return entry
    if isinstance(entry_range, dict):
        low = _positive(entry_range.get("low"))
        high = _positive(entry_range.get("high"))
        if low is not None and high is not None:
            if low > high:
                raise ValueError("entry_range_inverted")
            return (low + high) / 2.0
    return None


def validate_entry_candidate_geometry(
    *,
    direction: str,
    entry: float | None,
    entry_range: dict[str, Any] | None,
    stop: float | None,
    target: float | None,
    reference_price: float,
) -> list[str]:
    """Return objective risk codes; empty list means geometry is acceptable for evaluation."""
    codes: list[str] = []
    normalized = direction.strip().lower()
    if normalized not in {"long", "short"}:
        return codes

    entry_ref = entry_reference(entry, entry_range)
    stop_val = _positive(stop)
    target_val = _positive(target)

    if stop_val is None:
        codes.append("invalid_stop_geometry")
        return codes

    if normalized == "long":
        if stop_val >= (entry_ref or reference_price):
            codes.append("invalid_stop_geometry")
        if target_val is not None and target_val <= (entry_ref or reference_price):
            codes.append("invalid_target_geometry")
    else:
        if stop_val <= (entry_ref or reference_price):
            codes.append("invalid_stop_geometry")
        if target_val is not None and target_val >= (entry_ref or reference_price):
            codes.append("invalid_target_geometry")
    return codes
