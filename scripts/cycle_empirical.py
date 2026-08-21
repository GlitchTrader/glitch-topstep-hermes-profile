"""Structured per-cycle samples for offline outcome research (Trail D)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import append_jsonl, utc_now


def record_cycle_empirical(state: Path, record: dict[str, Any]) -> None:
    payload = {
        "schema_version": "glitch.topstep.cycle_empirical.v1",
        "recorded_utc": utc_now(),
        **record,
    }
    append_jsonl(state / "cycle-empirical.jsonl", payload)


def empirical_from_decision(
    *,
    packet: dict[str, Any],
    intent: dict[str, Any],
    invocation_reason: str,
    phase: str,
    delivery_classification: str | None = None,
) -> dict[str, Any]:
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    universe = packet.get("market_universe") if isinstance(packet.get("market_universe"), dict) else {}
    freshness = universe.get("universe_freshness") if isinstance(universe.get("universe_freshness"), dict) else {}
    continuity = None
    current_cycle = packet.get("CURRENT_CYCLE")
    if isinstance(current_cycle, dict):
        gap = current_cycle.get("continuity_gap")
        if isinstance(gap, dict):
            continuity = gap.get("present")
    return {
        "phase": phase,
        "packet_id": str(packet.get("packet_id") or intent.get("packet_id") or ""),
        "instrument": str(intent.get("instrument") or packet.get("instrument") or ""),
        "action": str(intent.get("action") or ""),
        "confidence": intent.get("confidence"),
        "invocation_reason": invocation_reason,
        "regime_detected": intent.get("regime_detected"),
        "delivery_classification": delivery_classification,
        "total_open_contracts": account.get("total_open_contracts"),
        "instrument_open_contracts": account.get("instrument_open_contracts"),
        "ranking_freshness_valid": freshness.get("ranking_freshness_valid"),
        "ranking_freshness_skew_ms": freshness.get("ranking_freshness_skew_ms"),
        "continuity_gap_present": continuity,
    }
