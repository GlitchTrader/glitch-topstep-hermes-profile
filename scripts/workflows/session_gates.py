"""Session and market-quiescence gates for flat cognition (GTHP-018)."""

from __future__ import annotations

import math
import os
from typing import Any

from workflows.wake_triggers import order_flow_window


def packet_positioned(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    if not isinstance(account, dict):
        return False
    return int(account.get("instrument_open_contracts") or 0) != 0


def respect_session_gate_enabled() -> bool:
    return os.environ.get("GLITCH_TOPSTEP_RESPECT_SESSION_GATE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def session_gate_override_enabled() -> bool:
    return os.environ.get("GLITCH_TOPSTEP_SESSION_GATE_OVERRIDE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def packet_session_closed(packet: dict[str, Any]) -> bool:
    session = packet.get("session")
    if not isinstance(session, dict):
        return False
    return session.get("entry_window_open") is False


def packet_session_phase(packet: dict[str, Any]) -> str | None:
    session = packet.get("session")
    if not isinstance(session, dict):
        return None
    phase = session.get("phase")
    if isinstance(phase, str) and phase.strip():
        return phase.strip()
    return None


def session_maintenance_skip_details(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """GTHP-018 follow-on: skip flat Luna during gateway session.phase=maintenance."""
    if directive is not None or packet_positioned(packet):
        return None
    phase = packet_session_phase(packet)
    if phase != "maintenance":
        return None
    return {
        "reason": "session_maintenance",
        "session_phase": phase,
    }


def flat_outside_session_window(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> bool:
    if not respect_session_gate_enabled() or session_gate_override_enabled():
        return False
    if directive is not None or packet_positioned(packet):
        return False
    return packet_session_closed(packet)


def _env_truthy(name: str, *, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def market_quiescence_gate_enabled() -> bool:
    """GTHP-018: skip flat Luna when quote is stale and tape is quiescent."""
    if _env_truthy("GLITCH_TOPSTEP_SKIP_MARKET_QUIESCENT", default="false"):
        return True
    # ponytail: legacy alias until operators migrate .env
    return _env_truthy("GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE")


def max_quiescent_trade_count_60s() -> int:
    try:
        return max(0, int(os.environ.get("GLITCH_TOPSTEP_QUIESCENT_MAX_TRADE_COUNT_60S", "0")))
    except ValueError:
        return 0


def packet_stream_health(packet: dict[str, Any]) -> dict[str, Any] | None:
    stream_health = packet.get("stream_health")
    if isinstance(stream_health, dict) and stream_health:
        return stream_health
    return None


def packet_trade_count_60s(packet: dict[str, Any]) -> int | None:
    stream_health = packet_stream_health(packet)
    if stream_health is not None:
        trade_count = stream_health.get("trade_count_60s")
        if isinstance(trade_count, bool):
            pass
        elif isinstance(trade_count, int):
            return trade_count
        elif isinstance(trade_count, float) and math.isfinite(trade_count):
            return int(trade_count)
    window = order_flow_window(packet, 60)
    if window is None:
        return None
    trade_count = window.get("trade_count")
    if isinstance(trade_count, bool):
        return None
    if isinstance(trade_count, int):
        return trade_count
    if isinstance(trade_count, float) and math.isfinite(trade_count):
        return int(trade_count)
    return None


def packet_quote_age_ms(packet: dict[str, Any]) -> float | None:
    observation = quote_age_observation(packet)
    return observation.get("normalized_quote_age_ms")


def packet_raw_quote_age_ms(packet: dict[str, Any]) -> float | None:
    observation = quote_age_observation(packet)
    raw = observation.get("raw_quote_age_ms")
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


def quote_age_observation(packet: dict[str, Any]) -> dict[str, Any]:
    from common import max_quote_age_ms

    stream_health = packet_stream_health(packet)
    data_quality = (
        packet.get("data_quality")
        if isinstance(packet.get("data_quality"), dict)
        else {}
    )
    sources = [source for source in (stream_health, data_quality) if isinstance(source, dict)]
    issues: list[str] = []
    raw: float | None = None
    for source in sources:
        source_issues = source.get("issues")
        if isinstance(source_issues, list):
            issues.extend(str(item) for item in source_issues)
        preserved = source.get("raw_quote_age_ms")
        if isinstance(preserved, (int, float)) and not isinstance(preserved, bool):
            candidate = float(preserved)
            raw = candidate if raw is None else min(raw, candidate)
            continue
        quote_age = source.get("quote_age_ms")
        if isinstance(quote_age, (int, float)) and not isinstance(quote_age, bool):
            candidate = float(quote_age)
            if candidate < 0:
                raw = candidate if raw is None else min(raw, candidate)

    primary = stream_health if stream_health is not None else data_quality
    primary_age = None
    if isinstance(primary, dict):
        quote_age = primary.get("quote_age_ms")
        if isinstance(quote_age, (int, float)) and not isinstance(quote_age, bool):
            primary_age = float(quote_age)
    normalized = (
        0.0
        if primary_age is not None and primary_age < 0
        else (
            float(max(0, int(round(primary_age))))
            if primary_age is not None
            else None
        )
    )
    clock_skew = (
        (raw is not None and raw < 0)
        or "quote_clock_skew" in issues
        or any(source.get("clock_skew_detected") is True for source in sources)
    )
    return {
        "raw_quote_age_ms": int(round(raw)) if raw is not None and raw < 0 else None,
        "normalized_quote_age_ms": normalized,
        "clock_skew_detected": clock_skew,
        "max_quote_age_ms": max_quote_age_ms(),
    }


def packet_reconnect_pending(packet: dict[str, Any]) -> bool:
    stream_health = packet_stream_health(packet)
    if stream_health is not None and stream_health.get("reconnect_pending") is True:
        return True
    data_quality = (
        packet.get("data_quality")
        if isinstance(packet.get("data_quality"), dict)
        else {}
    )
    issues = data_quality.get("issues")
    if isinstance(issues, list):
        return any(
            issue in issues
            for issue in ("market_stream_reconnecting", "user_stream_reconnecting")
        )
    return False


def packet_quote_stale(packet: dict[str, Any]) -> bool:
    from common import max_quote_age_ms

    if packet_reconnect_pending(packet):
        return False
    data_quality = (
        packet.get("data_quality")
        if isinstance(packet.get("data_quality"), dict)
        else {}
    )
    issues = data_quality.get("issues")
    if isinstance(issues, list) and "quote_stale" in issues:
        return True
    quote_age = packet_quote_age_ms(packet)
    if quote_age is not None:
        return quote_age > max_quote_age_ms()
    return False


def market_quiescent_skip_details(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not market_quiescence_gate_enabled():
        return None
    if directive is not None or packet_positioned(packet):
        return None
    if packet_reconnect_pending(packet):
        return None
    data_quality = (
        packet.get("data_quality")
        if isinstance(packet.get("data_quality"), dict)
        else {}
    )
    if data_quality.get("state_complete") is not True:
        return None
    if not packet_quote_stale(packet):
        return None
    trade_count = packet_trade_count_60s(packet)
    if trade_count is None or trade_count > max_quiescent_trade_count_60s():
        return None
    quote_observation = quote_age_observation(packet)
    details: dict[str, Any] = {
        "reason": "market_quiescent",
        **quote_observation,
        "quote_age_ms": quote_observation["normalized_quote_age_ms"],
        "trade_count_60s": trade_count,
        "order_flow_trade_count_60s": trade_count,
    }
    if packet_stream_health(packet) is not None:
        details["evidence_source"] = "stream_health"
    return details


def market_quiescent_skip_reason(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> str | None:
    details = market_quiescent_skip_details(packet, directive)
    return str(details["reason"]) if details else None


def stale_gateway_skip_reason(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> str | None:
    """Deprecated alias for market_quiescent_skip_reason (GTHP-018)."""
    return market_quiescent_skip_reason(packet, directive)
