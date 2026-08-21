"""NT parity helpers adapted for Glitch Topstep Hermes profile."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from distribution_manifest import PROMPT_VERSION
from workflows.delivery_recovery import (
    GATEWAY_COGNITIVE_REJECTION_CODES,
    GATEWAY_SYSTEM_DEFECT_CODES,
    classify_delivery_result,
    classify_gateway_rejection,
)
from workflows.gateway_session import (
    clear_delivery_wire,
    deliver_packet_intent,
    delivery_wire_path,
    is_registered_delivery_conflict,
    load_delivery_wire,
    reconcile_registered_delivery,
    save_delivery_wire,
)
from workflows.intent_outbox import (
    discard_stale_outbox_intent,
    discard_superseded_delivery_error,
    discard_superseded_pending_outbox,
    frame_for_packet_id,
    intent_is_entry,
    packet_for_outbox_id,
    pending_outbox,
    prune_delivered_outboxes,
    supersession_discard_reason,
)
from common import (
    append_jsonl,
    parse_utc,
    read_json,
    read_jsonl,
    read_optional_json,
    request_json,
    utc_now,
    write_json_atomic,
)

CURRENT_PLAN_SCHEMA = "glitch.topstep.portfolio_plan.v1"
CURRENT_GUIDANCE_SCHEMA = "glitch.topstep.guidance.v1"
RETRYABLE_ATTEMPT_STATUSES = frozenset(
    {"failed", "execution_failed", "delivery_incomplete"}
)


from workflows.wake_triggers import (
    WAKE_TRIGGER_SCHEMA,
    WAKE_TRIGGER_TYPES,
    SESSION_PHASE_VALUES,
    clear_pending_wake_invocation,
    cycle_wake_fields,
    evaluate_wake_triggers,
    explicit_price_crosses,
    order_flow_window,
    packet_current_price,
    packet_one_minute_range,
    persist_wake_triggers,
    read_pending_wake_invocation,
    record_wake_trigger_fire,
    require_explicit_wake_triggers,
    validate_wake_triggers,
    wake_reason_label,
    wake_trigger_fired,
    wake_trigger_key,
    wake_trigger_path,
    write_pending_wake_invocation,
)
def monitor_should_launch_cycle(
    state: Path,
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
    *,
    flat_decision_interval_minutes: int,
) -> dict[str, Any] | None:
    wake_detail = evaluate_wake_triggers(state, packet)
    if not wake_detail:
        return None
    reason = invocation_reason(
        packet,
        state,
        directive,
        flat_decision_interval_minutes=flat_decision_interval_minutes,
    )
    if reason is not None and reason not in {"condition_change"}:
        return None
    lock_path = state / "direct-cycle.lock"
    if lock_path.is_file():
        return None
    return wake_detail


def last_evidence_exists(state: Path) -> bool:
    return (state / "last-evidence.json").is_file()


def latest_prior_attempt(state: Path, packet_id: str) -> dict[str, Any] | None:
    attempts_dir = state / "attempts"
    if not attempts_dir.is_dir():
        return None
    latest_path: Path | None = None
    latest_mtime = 0.0
    for path in attempts_dir.glob("*.json"):
        if path.stem == packet_id:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= latest_mtime:
            latest_mtime = mtime
            latest_path = path
    if latest_path is None:
        return None
    try:
        value = read_json(latest_path)
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def packet_positioned(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    if not isinstance(account, dict):
        return False
    return int(account.get("instrument_open_contracts") or 0) != 0


def respect_session_gate_enabled() -> bool:
    import os

    return os.environ.get("GLITCH_TOPSTEP_RESPECT_SESSION_GATE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def session_gate_override_enabled() -> bool:
    import os

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
    import os

    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def market_quiescence_gate_enabled() -> bool:
    """GTHP-018: skip flat Luna when quote is stale and tape is quiescent."""
    if _env_truthy("GLITCH_TOPSTEP_SKIP_MARKET_QUIESCENT", default="false"):
        return True
    # ponytail: legacy alias until operators migrate .env
    return _env_truthy("GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE")


def max_quiescent_trade_count_60s() -> int:
    import os

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


PACKET_PROTECTION_STATUSES = frozenset({
    "pending",
    "confirmed",
    "failed",
    "unknown",
})


def packet_protection_status(packet: dict[str, Any]) -> str | None:
    """GTHP-020: Hermes-facing bracket verification state when positioned."""
    if not packet_positioned(packet):
        return None
    protection = packet.get("protection")
    if not isinstance(protection, dict):
        return "unknown"
    status = protection.get("protection_status")
    if isinstance(status, str) and status in PACKET_PROTECTION_STATUSES:
        return status
    # ponytail: pre-0.1.6 gateways expose protection.status only
    legacy = protection.get("status")
    if legacy == "proven":
        return "confirmed"
    if legacy == "pending":
        return "pending"
    if legacy == "incomplete":
        return "failed"
    return "unknown"


def protection_status_allows_amendment(status: str | None) -> bool:
    return status == "confirmed"


def protection_status_management_guidance(status: str | None) -> str | None:
    if status is None:
        return None
    if status == "confirmed":
        return (
            "protection.protection_status is confirmed — SL/TP verified on venue; "
            "full management including MOVE_STOP and MOVE_TP is available."
        )
    if status == "pending":
        return (
            "protection.protection_status is pending — venue brackets may still be landing; "
            "prefer HOLD, name the wait in the audit, and use EXIT if protection fails to confirm."
        )
    if status == "failed":
        return (
            "protection.protection_status is failed — venue SL/TP not verified within the gateway "
            "timeout; prioritize risk-reducing EXIT; do not submit MOVE_STOP or MOVE_TP."
        )
    return (
        "protection.protection_status is unknown — reconciliation incomplete; "
        "prefer HOLD or risk-reducing EXIT; do not submit MOVE_STOP or MOVE_TP."
    )


def invocation_reason(
    packet: dict[str, Any],
    state: Path,
    directive: dict[str, Any] | None,
    *,
    flat_decision_interval_minutes: int,
) -> str | None:
    packet_id = str(packet.get("packet_id") or "")
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    is_positioned = int(account.get("instrument_open_contracts") or 0) != 0

    if directive is not None:
        return "operator_directive"
    if is_positioned:
        return "positioned"
    if flat_outside_session_window(packet, directive):
        if wake_trigger_fired(state, packet):
            return "condition_change"
        return None
    if wake_trigger_fired(state, packet):
        return "condition_change"
    if not last_evidence_exists(state):
        return "first_packet"
    prior = latest_prior_attempt(state, packet_id)
    if prior is not None and prior.get("status") in RETRYABLE_ATTEMPT_STATUSES:
        return "retry_after_failure"
    minute = parse_utc(packet["created_utc"]).minute
    if minute % flat_decision_interval_minutes == 0:
        return "scheduled"
    return None


def read_trading_learning_artifact(path: Path, schema_version: str) -> dict[str, Any] | None:
    value = read_optional_json(path)
    if not value or value.get("schema_version") != schema_version:
        return None
    if value.get("trading_influence") != "outcome_backed":
        return None
    prompt_version = value.get("prompt_version") or value.get("decision_prompt_version")
    if prompt_version != PROMPT_VERSION:
        return None
    return value


def _truncate_text(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _order_flow_delta(packet: dict[str, Any], seconds: int) -> float | None:
    window = order_flow_window(packet, seconds)
    if not isinstance(window, dict):
        return None
    delta = window.get("rolling_delta")
    if isinstance(delta, (int, float)) and not isinstance(delta, bool):
        return float(delta)
    return None


def compute_cycle_evidence_delta(
    current_packet: dict[str, Any],
    prior_frame: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(prior_frame, dict):
        return None
    prior_packet = prior_frame.get("packet")
    if not isinstance(prior_packet, dict):
        return None

    current_price = packet_current_price(current_packet)
    prior_price = packet_current_price(prior_packet)
    delta: dict[str, Any] = {
        "prior_minute_id": prior_frame.get("minute_id"),
        "prior_captured_utc": prior_frame.get("captured_utc"),
    }
    if current_price is not None and prior_price is not None:
        price_change = current_price - prior_price
        delta["price_change"] = round(price_change, 4)
        if prior_price:
            delta["price_change_bps"] = round(
                (price_change / prior_price) * 10_000,
                4,
            )
    for seconds in (15, 60, 300):
        current_value = _order_flow_delta(current_packet, seconds)
        prior_value = _order_flow_delta(prior_packet, seconds)
        if current_value is not None or prior_value is not None:
            delta[f"delta_{seconds}s"] = {
                "current": current_value,
                "prior": prior_value,
                "change": (
                    None
                    if current_value is None or prior_value is None
                    else round(current_value - prior_value, 4)
                ),
            }
    if len(delta) <= 2 and current_price is None:
        return None
    return delta


def repeated_change_condition_warning(
    decisions: list[dict[str, Any]],
    *,
    min_repeat: int = 2,
) -> str | None:
    if len(decisions) < min_repeat:
        return None
    recent = decisions[-min_repeat:]
    values: list[str] = []
    for row in recent:
        intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
        audit = (
            intent.get("decision_audit")
            if isinstance(intent.get("decision_audit"), dict)
            else {}
        )
        text = str(audit.get("change_condition") or "").strip().lower()
        if not text:
            return None
        values.append(text)
    if len(set(values)) == 1:
        return (
            "Prior change_condition text repeated across recent cycles; "
            "rewrite with current-cycle price, flow, and structure deltas."
        )
    return None


def delivery_diagnostic_detail(result: dict[str, Any]) -> dict[str, Any]:
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    detail: dict[str, Any] = {}
    for key in ("code", "field", "error", "message", "status"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            detail[key] = value.strip()[:240]
    http_status = result.get("http_status")
    if isinstance(http_status, int):
        detail["http_status"] = http_status
    return detail


FULL_CHANGE_CONDITION_TAIL = 2


def compact_decision_row(
    row: dict[str, Any],
    *,
    preserve_change_condition: bool = False,
) -> dict[str, Any]:
    intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
    audit = (
        intent.get("decision_audit")
        if isinstance(intent.get("decision_audit"), dict)
        else {}
    )
    change_condition = str(audit.get("change_condition") or "")
    if preserve_change_condition:
        change_condition_value = change_condition.strip() or None
    else:
        change_condition_value = (
            _truncate_text(change_condition, 240) if change_condition else None
        )
    return {
        "recorded_utc": row.get("recorded_utc"),
        "packet_id": row.get("packet_id"),
        "action": intent.get("action"),
        "intent_id": intent.get("intent_id"),
        "reason": _truncate_text(str(intent.get("reason") or ""), 240) or None,
        "final_choice": audit.get("final_choice"),
        "change_condition": change_condition_value,
    }


def compact_receipt_row(row: dict[str, Any]) -> dict[str, Any] | None:
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    status = body.get("status") or row.get("status")
    code = body.get("code") or row.get("rejection_reason")
    http_status = result.get("http_status")
    compact = {
        "recorded_utc": row.get("recorded_utc"),
        "intent_id": row.get("intent_id"),
        "packet_id": row.get("packet_id"),
        "http_status": http_status,
        "status": status,
        "code": code,
    }
    for detail_key in ("field", "error", "message"):
        detail_value = body.get(detail_key)
        if isinstance(detail_value, str) and detail_value.strip():
            compact[detail_key] = detail_value.strip()[:240]
    if not any(
        compact.get(key) is not None
        for key in ("http_status", "status", "code", "field", "error", "message")
    ):
        return None
    return compact


def compact_outcome_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "outcome_id": row.get("outcome_id"),
        "recorded_utc": row.get("recorded_utc"),
        "classification": row.get("classification"),
        "exit_reason": row.get("exit_reason"),
        "r_multiple": row.get("r_multiple"),
        "net_pnl_usd": row.get("net_pnl_usd"),
    }


def summarize_outcomes_for_cycle(
    outcomes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not outcomes:
        return None
    net_pnl = 0.0
    fees = 0.0
    longs = shorts = wins = losses = inconclusive = 0
    for row in outcomes:
        pnl = row.get("realized_pnl_usd")
        if pnl is None:
            pnl = row.get("net_pnl_usd")
        if isinstance(pnl, (int, float)) and not isinstance(pnl, bool):
            pnl_value = float(pnl)
            net_pnl += pnl_value
            if row.get("learning_eligible") is False:
                inconclusive += 1
            elif pnl_value > 0:
                wins += 1
            elif pnl_value < 0:
                losses += 1
            else:
                inconclusive += 1
        else:
            inconclusive += 1
        fee = row.get("fees_usd")
        if isinstance(fee, (int, float)) and not isinstance(fee, bool):
            fees += float(fee)
        side = str(row.get("side") or "").upper()
        if side == "LONG":
            longs += 1
        elif side == "SHORT":
            shorts += 1
    trade_count = len(outcomes)
    net_after_fees = net_pnl - fees
    return {
        "trade_count": trade_count,
        "net_pnl_usd": round(net_pnl, 2),
        "fees_usd": round(fees, 2),
        "net_after_fees_usd": round(net_after_fees, 2),
        "expectancy_after_fees_usd": round(net_after_fees / trade_count, 4),
        "longs": longs,
        "shorts": shorts,
        "wins": wins,
        "losses": losses,
        "inconclusive": inconclusive,
    }


def compact_cycle_ledger_context(
    *,
    decisions: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    compact_decisions = [
        compact_decision_row(
            row,
            preserve_change_condition=index >= len(decisions) - FULL_CHANGE_CONDITION_TAIL,
        )
        for index, row in enumerate(decisions)
    ]
    compact_receipts = [
        item
        for item in (compact_receipt_row(row) for row in receipts)
        if item is not None
    ]
    return {
        "decisions": compact_decisions,
        "receipts": compact_receipts,
        "outcomes": [compact_outcome_row(row) for row in outcomes],
        "outcome_summary": summarize_outcomes_for_cycle(outcomes),
    }


def learning_context(supervisor: Path) -> dict[str, Any]:
    from learning_clusters import build_similarity_clusters, summarize_clusters

    overlay = read_optional_json(supervisor / "active-cognitive-overlay.json")
    if (
        not overlay
        or overlay.get("status") not in {"active", "promoted"}
        or not (overlay.get("replacement_text") or overlay.get("instruction"))
    ):
        overlay = None
    return {
        "current_plan": read_trading_learning_artifact(
            supervisor / "current-plan.json",
            CURRENT_PLAN_SCHEMA,
        ),
        "current_guidance": read_trading_learning_artifact(
            supervisor / "current-guidance.json",
            CURRENT_GUIDANCE_SCHEMA,
        ),
        "active_cognitive_overlay": overlay,
        "outcome_backed_lessons": summarized_outcome_backed_lessons(supervisor),
        "similarity_clusters": summarize_clusters(
            build_similarity_clusters(read_jsonl(supervisor / "decision-episodes.jsonl")),
            limit=3,
        ),
    }


def summarized_outcome_backed_lessons(
    supervisor: Path,
    max_rows: int = 5,
    max_chars: int = 4_000,
) -> list[dict[str, Any]]:
    rows = [
        {
            "lesson_id": row.get("lesson_id"),
            "summary": row.get("summary") or row.get("lesson"),
            "source_review_id": row.get("source_review_id"),
            "recorded_utc": row.get("recorded_utc"),
        }
        for row in read_jsonl(supervisor / "lessons.jsonl")
        if row.get("trading_influence") == "outcome_backed"
    ]
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for row in reversed(rows):
        row_chars = len(json.dumps(row, separators=(",", ":"), ensure_ascii=False))
        if len(selected) >= max_rows or used_chars + row_chars > max_chars:
            break
        selected.append(row)
        used_chars += row_chars
    return list(reversed(selected))


def apply_cognitive_overlay(prompt: str, overlay: dict[str, Any] | None) -> str:
    if not isinstance(overlay, dict) or overlay.get("status") not in {"active", "promoted"}:
        return prompt
    if overlay.get("operation") != "replace" or overlay.get("target") != "core_prompt":
        return prompt
    expected = str(overlay.get("expected_old_text") or "")
    replacement = str(overlay.get("replacement_text") or "")
    expected_hash = str(overlay.get("expected_old_sha256") or "")
    if (
        not expected
        or not replacement
        or len(expected) > 600
        or len(replacement) > 600
        or prompt.count(expected) != 1
        or hashlib.sha256(expected.encode("utf-8")).hexdigest() != expected_hash
    ):
        return prompt
    return prompt.replace(expected, replacement, 1)


def active_trade_state(state: Path, packet: dict[str, Any]) -> dict[str, Any]:
    """Simplified Topstep open-trade continuity from packet + local ledger."""
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    net = int(account.get("instrument_open_contracts") or 0)
    decisions = read_jsonl(state / "decisions.jsonl")
    outcomes = read_jsonl(state / "outcomes.jsonl")
    closed_entries = {str(row.get("intent_id")) for row in outcomes if row.get("intent_id")}
    previous = read_optional_json(state / "supervisor" / "active-trade-state.json") or {}
    previous_trade = previous.get("trade") if isinstance(previous.get("trade"), dict) else {}

    trade: dict[str, Any] | None = None
    if net != 0:
        side = "long" if net > 0 else "short"
        open_entries: list[dict[str, Any]] = []
        management: list[dict[str, Any]] = []
        account_name = str(account.get("name") or packet.get("account", {}).get("name") or "")
        for row in decisions:
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            if str(intent.get("account") or "") != account_name:
                continue
            action = str(intent.get("action") or "")
            intent_id = str(intent.get("intent_id") or "")
            if action in {"ENTER_LONG", "ENTER_SHORT"} and intent_id not in closed_entries:
                if (action == "ENTER_LONG") == (side == "long"):
                    open_entries.append(intent)
            elif action in {"HOLD", "EXIT"}:
                management.append(intent)

        entry_ids = [str(row.get("intent_id")) for row in open_entries if row.get("intent_id")]
        same_trade = (
            previous_trade.get("entry_intent_ids") == entry_ids
            and previous_trade.get("side") == side
        )
        unrealized = float(account.get("unrealized_pnl") or 0)
        peak = (
            max(float(previous_trade.get("peak_unrealized_pnl_usd", unrealized) or unrealized), unrealized)
            if same_trade
            else unrealized
        )
        trough = (
            min(float(previous_trade.get("trough_unrealized_pnl_usd", unrealized) or unrealized), unrealized)
            if same_trade
            else unrealized
        )
        created_values = [str(row.get("created_utc")) for row in open_entries if row.get("created_utc")]
        entry_utc = min(created_values) if created_values else str(previous_trade.get("entry_decision_utc") or "")
        if entry_utc:
            management = [row for row in management if str(row.get("created_utc") or "") >= entry_utc]
        try:
            age_seconds = max(
                0,
                int((datetime.now(timezone.utc) - parse_utc(entry_utc)).total_seconds()),
            )
        except (TypeError, ValueError):
            age_seconds = None
        trade = {
            "account": account_name,
            "instrument": packet.get("instrument"),
            "side": side,
            "quantity": abs(net),
            "unrealized_pnl_usd": unrealized,
            "peak_unrealized_pnl_usd": peak,
            "trough_unrealized_pnl_usd": trough,
            "rollback_from_peak_usd": peak - unrealized,
            "entry_decision_utc": entry_utc or None,
            "trade_age_seconds": age_seconds,
            "entry_intent_ids": entry_ids,
            "entry_plans": [
                {
                    "intent_id": row.get("intent_id"),
                    "quantity": row.get("quantity"),
                    "planned_stop": row.get("stop_loss"),
                    "planned_targets": [
                        row.get(key)
                        for key in ("take_profit_1", "take_profit_2", "take_profit_3")
                        if row.get(key) is not None
                    ],
                    "reason": row.get("reason"),
                }
                for row in open_entries
            ],
            "recent_management": [
                {
                    "intent_id": row.get("intent_id"),
                    "created_utc": row.get("created_utc"),
                    "action": row.get("action"),
                    "stop_loss": row.get("stop_loss"),
                    "take_profit_1": row.get("take_profit_1"),
                    "reason": row.get("reason"),
                }
                for row in management[-20:]
            ],
        }

    value = {
        "schema_version": "glitch.topstep.active_trade_state.v1",
        "recorded_utc": utc_now(),
        "trade": trade,
    }
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    write_json_atomic(supervisor / "active-trade-state.json", value)
    return value


def outcome_execution_summary(outcome: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "exit_reason",
        "entry_price",
        "exit_price",
        "stop_price",
        "target_price",
        "mae_usd",
        "mfe_usd",
        "mae_ticks",
        "mfe_ticks",
        "initial_risk_usd",
        "r_multiple",
        "protection_confirmed",
        "side",
        "quantity",
        "fills",
    )
    summary = {key: outcome.get(key) for key in keys if key in outcome}
    attribution = outcome.get("attribution")
    if isinstance(attribution, dict):
        if attribution.get("protection_status"):
            summary["protection_status"] = attribution["protection_status"]
        for key in ("closing_order_id", "stop_order_id", "target_order_id", "entry_order_id"):
            if key in attribution:
                summary[key] = attribution.get(key)
    evidence = outcome.get("evidence")
    if isinstance(evidence, dict) and evidence.get("order_ids") is not None:
        summary["order_ids"] = evidence.get("order_ids")
    return summary


def debrief_facts(
    outcome: dict[str, Any],
    outcome_execution: dict[str, Any],
    entry_intent: dict[str, Any] | None,
) -> dict[str, Any]:
    intent = entry_intent if isinstance(entry_intent, dict) else {}
    return {
        "outcome_id": outcome.get("outcome_id"),
        "intent_id": outcome.get("intent_id"),
        "account": outcome.get("account"),
        "instrument": outcome.get("instrument"),
        "entry_utc": outcome.get("entry_utc"),
        "exit_utc": outcome.get("exit_utc"),
        "realized_pnl_usd": outcome.get("realized_pnl_usd"),
        "fees_usd": outcome.get("fees_usd"),
        "learning_eligible": outcome.get("learning_eligible"),
        "entry_action": intent.get("action"),
        "exit_reason": outcome_execution.get("exit_reason"),
        "mae_usd": outcome_execution.get("mae_usd"),
        "mfe_usd": outcome_execution.get("mfe_usd"),
        "initial_risk_usd": outcome_execution.get("initial_risk_usd"),
        "r_multiple": outcome_execution.get("r_multiple"),
        "protection_status": outcome_execution.get("protection_status"),
        "entry_price": outcome_execution.get("entry_price", outcome.get("entry_price")),
        "exit_price": outcome_execution.get("exit_price", outcome.get("exit_price")),
        "stop_price": outcome_execution.get("stop_price", outcome.get("stop_price")),
        "target_price": outcome_execution.get("target_price", outcome.get("target_price")),
        "side": outcome_execution.get("side", outcome.get("side")),
        "quantity": outcome_execution.get("quantity", outcome.get("quantity")),
        "fills": outcome_execution.get("fills", outcome.get("fills")),
        "order_ids": outcome_execution.get("order_ids"),
        "closing_order_id": outcome_execution.get("closing_order_id"),
        "stop_order_id": outcome_execution.get("stop_order_id"),
        "target_order_id": outcome_execution.get("target_order_id"),
        "entry_order_id": outcome_execution.get("entry_order_id"),
    }


def collect_market_path(
    frames_root: Path,
    entry: datetime,
    exit_time: datetime,
) -> list[dict[str, Any]]:
    """Collect minute-frame last/high/low between entry and exit (inclusive).

    Frames are named by minute_id (e.g. 20260811T2059Z.json), not packet_id UUID.
    Matching on packet_id therefore never finds a path — iterate by packet created_utc.
    """
    market_path: list[dict[str, Any]] = []
    if not frames_root.is_dir():
        return market_path
    for path in sorted(frames_root.glob("*.json")):
        frame = read_optional_json(path)
        if not isinstance(frame, dict):
            continue
        packet = frame.get("packet")
        if not isinstance(packet, dict):
            continue
        market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
        stamp_raw = packet.get("created_utc") or frame.get("captured_utc")
        try:
            stamp = parse_utc(stamp_raw)
        except (TypeError, ValueError):
            continue
        if stamp < entry:
            continue
        if stamp > exit_time:
            break
        try:
            close = float(market["last"])
        except (KeyError, TypeError, ValueError):
            continue
        market_path.append(
            {
                "minute_id": frame.get("minute_id"),
                "close": close,
                "high": float(market.get("high", close)),
                "low": float(market.get("low", close)),
            }
        )
    return market_path


def stable_facts_sha256(facts: dict[str, Any]) -> str:
    body = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def debrief_prompt_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt_rows: list[dict[str, Any]] = []
    for row in rows:
        prompt_rows.append(
            {
                "facts": row["facts"],
                "facts_sha256": row["facts_sha256"],
                "entry_decision": row.get("entry_decision"),
                "market_path": row.get("market_path"),
                "related_decision_count": len(row.get("related_decisions") or []),
            }
        )
    return prompt_rows


def mark_attempt_from_receipt(state: Path, packet_id: str, result: dict[str, Any]) -> None:
    path = state / "attempts" / f"{packet_id}.json"
    if not path.is_file():
        return
    attempt = read_json(path)
    classification = classify_delivery_result(result)
    if classification == "terminal_rejection":
        attempt["status"] = "execution_failed"
    elif classification == "transport_uncertain":
        attempt["status"] = "delivery_incomplete"
    else:
        attempt["status"] = "completed"
    attempt["completed_utc"] = utc_now()
    write_json_atomic(path, attempt)


def defer_instrument_scope_mismatch(
    state: Path,
    packet_id: str,
    intent: dict[str, Any],
    current_packet: dict[str, Any],
) -> bool:
    """Keep management intents for another exact instrument until its scope is active."""
    intent_instrument = str(intent.get("instrument") or "").strip().upper()
    packet_instrument = str(current_packet.get("instrument") or "").strip().upper()
    if not intent_instrument or not packet_instrument or intent_instrument == packet_instrument:
        return False
    marker = state / "deferred-scope" / f"{packet_id}.json"
    if not marker.is_file():
        write_json_atomic(
            marker,
            {
                "schema_version": "glitch.topstep.deferred_scope.v1",
                "recorded_utc": utc_now(),
                "packet_id": packet_id,
                "intent_id": str(intent.get("intent_id") or ""),
                "intent_instrument": intent_instrument,
                "active_instrument": packet_instrument,
                "action": str(intent.get("action") or ""),
            },
        )
        append_jsonl(
            state / "events.jsonl",
            {
                "schema_version": "glitch.topstep.cycle_event.v2",
                "event": "intent_deferred_instrument_scope",
                "recorded_utc": utc_now(),
                "packet_id": packet_id,
                "intent_id": str(intent.get("intent_id") or ""),
                "intent_instrument": intent_instrument,
                "active_instrument": packet_instrument,
                "action": str(intent.get("action") or ""),
            },
        )
    return True


ENTRY_GEOMETRY_ERRORS = frozenset({
    "long_geometry_invalid",
    "short_geometry_invalid",
    "entry_range_superseded",
    "entry_scope_superseded",
    "entry_intent_expired",
})


def discard_unexecutable_entry_outbox(
    state: Path,
    outbox_path: Path,
    packet_id: str,
    intent: dict[str, Any],
    error: BaseException,
) -> bool:
    """Discard entry outbox when live quote no longer sits between stop and target.

    Pending outbox retries validate against the stored decision packet, then
    prepare_intent_for_delivery re-checks geometry and the frozen range on the
    fresh quote. Superseded entries are dropped once so the next cycle performs
    one fresh comparison; the old range is never widened.
    """
    if not intent_is_entry(intent):
        return False
    if str(error) not in ENTRY_GEOMETRY_ERRORS:
        return False
    try:
        outbox_path.unlink(missing_ok=True)
    except OSError:
        return False
    clear_delivery_wire(state, packet_id)
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "intent_discarded_geometry_invalid",
            "reason": str(error),
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": str(intent.get("intent_id") or ""),
            "action": str(intent.get("action") or ""),
            "stop_loss": intent.get("stop_loss"),
            "take_profit_1": intent.get("take_profit_1"),
        },
    )
    return True


FLAT_ABSTENTION_CLASSIFICATIONS = frozenset({
    "justified_abstention",
    "avoided_adverse_movement",
    "missed_directional_participation",
    "ambiguous",
})


def suggest_flat_abstention_classification(
    *,
    initial_price: float,
    forward_high: float,
    forward_low: float,
    forward_close: float,
    tick_size: float = 0.25,
) -> str:
    # ponytail: coarse price-path heuristic; Hermes may override in hourly review
    up = forward_high - initial_price
    down = initial_price - forward_low
    move = abs(forward_close - initial_price)
    noise = max(tick_size * 8, initial_price * 0.00005)
    if move <= noise and max(up, down) <= noise * 2:
        return "justified_abstention"
    if up > down * 1.5 and up > noise * 2:
        return "missed_directional_participation"
    if down > up * 1.5 and down > noise * 2:
        return "avoided_adverse_movement"
    return "ambiguous"


def compute_nothing_counterfactual(
    decision: dict[str, Any],
    forward_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return MFE/MAE ticks and abstention classification for flat NOTHING."""
    pre = decision.get("pre_decision_state")
    pre = pre if isinstance(pre, dict) else {}
    try:
        initial = float(pre.get("initial_price"))
    except (TypeError, ValueError):
        initial = float(forward_observations[0]["close"])
    highs = [float(row["high"]) for row in forward_observations]
    lows = [float(row["low"]) for row in forward_observations]
    closes = [float(row["close"]) for row in forward_observations]
    forward_high = max(highs)
    forward_low = min(lows)
    forward_close = closes[-1]
    tick_size = 0.25
    contract = decision.get("contract") if isinstance(decision.get("contract"), dict) else {}
    raw_tick = contract.get("tick_size")
    if isinstance(raw_tick, (int, float)) and not isinstance(raw_tick, bool) and raw_tick > 0:
        tick_size = float(raw_tick)
    up_ticks = (forward_high - initial) / tick_size
    down_ticks = (initial - forward_low) / tick_size
    classification = suggest_flat_abstention_classification(
        initial_price=initial,
        forward_high=forward_high,
        forward_low=forward_low,
        forward_close=forward_close,
        tick_size=tick_size,
    )
    if classification == "missed_directional_participation":
        mfe_ticks = up_ticks
        mae_ticks = down_ticks
    elif classification == "avoided_adverse_movement":
        mfe_ticks = up_ticks
        mae_ticks = down_ticks
    else:
        mfe_ticks = max(up_ticks, down_ticks)
        mae_ticks = min(up_ticks, down_ticks)
    return {
        "classification": classification,
        "mfe_ticks": round(mfe_ticks, 2),
        "mae_ticks": round(mae_ticks, 2),
    }


def _change_condition_price_met(
    change_condition: str,
    prior_price: float,
    next_price: float,
) -> bool:
    import re

    text = change_condition.lower()
    numbers = [
        float(match)
        for match in re.findall(r"\b\d+(?:\.\d+)?\b", change_condition)
    ]
    if not numbers:
        return False
    for level in numbers:
        if any(token in text for token in ("above", "over", "reclaim", "cross above")):
            if prior_price <= level < next_price:
                return True
        if any(token in text for token in ("below", "under", "break", "cross below")):
            if prior_price >= level > next_price:
                return True
        if abs(next_price - level) <= abs(prior_price - level) * 0.5:
            return True
    return False


def review_change_condition(
    prior_decision: dict[str, Any],
    next_frame: dict[str, Any],
) -> str:
    audit = prior_decision.get("decision_audit")
    if not isinstance(audit, dict):
        return "unknown"
    change = str(audit.get("change_condition") or "").strip()
    if not change:
        return "unknown"
    prior_packet = prior_decision.get("packet")
    if not isinstance(prior_packet, dict):
        prior_packet = {}
    next_packet = next_frame.get("packet") if isinstance(next_frame.get("packet"), dict) else {}
    prior_market = prior_packet.get("market") if isinstance(prior_packet.get("market"), dict) else {}
    next_market = next_packet.get("market") if isinstance(next_packet.get("market"), dict) else {}
    try:
        prior_price = float(prior_market.get("last"))
        next_price = float(next_market.get("last"))
    except (TypeError, ValueError):
        return "unknown"
    if not _change_condition_price_met(change, prior_price, next_price):
        return "unmet"
    subsequent = next_frame.get("subsequent_intent")
    if not isinstance(subsequent, dict):
        return "unknown"
    prior_action = str(prior_decision.get("action") or "")
    next_action = str(subsequent.get("action") or "")
    if next_action != prior_action:
        return "met_with_reassessment"
    next_audit = subsequent.get("decision_audit")
    if isinstance(next_audit, dict):
        for field in ("decisive_evidence", "change_condition", "final_choice"):
            if str(next_audit.get(field) or "") != str(audit.get(field) or ""):
                return "met_with_reassessment"
    return "met_without_reassessment"


def wait_for_packet_rollover(
    packet: dict[str, Any],
    wait_seconds: float,
    *,
    token: str,
) -> dict[str, Any]:
    if wait_seconds <= 0 or not packet:
        return packet
    try:
        created = parse_utc(packet["created_utc"])
        age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
    except (KeyError, TypeError, ValueError):
        return packet
    if age_seconds < 50:
        return packet
    packet_id = str(packet.get("packet_id") or "")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        status, candidate = request_json("/packet", token=token)
        if status == 200 and isinstance(candidate, dict):
            if str(candidate.get("packet_id") or "") != packet_id:
                return candidate
    return packet


def debrief_evidence(state: Path, outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = read_jsonl(state / "decisions.jsonl")
    receipts_by_packet: dict[str, dict[str, Any]] = {}
    for path in (state / "receipts").glob("*.json"):
        receipt = read_optional_json(path)
        if isinstance(receipt, dict):
            receipts_by_packet[path.stem] = receipt

    frames_root = state / "minute-frames"
    evidence: list[dict[str, Any]] = []
    for outcome in outcomes:
        intent_id = str(outcome.get("intent_id") or "")
        entry = parse_utc(outcome["entry_utc"])
        exit_time = parse_utc(outcome["exit_utc"])
        account = str(outcome.get("account") or "")

        related_decisions = []
        for row in decisions:
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            if str(intent.get("account") or "") != account:
                continue
            try:
                stamp = parse_utc(row.get("recorded_utc"))
            except (TypeError, ValueError):
                continue
            if entry - timedelta(seconds=90) <= stamp <= exit_time + timedelta(seconds=90):
                related_decisions.append(row)

        entry_row = next(
            (
                row
                for row in decisions
                if isinstance(row.get("intent"), dict)
                and str(row["intent"].get("intent_id") or "") == intent_id
            ),
            None,
        )
        entry_intent = entry_row.get("intent") if isinstance(entry_row, dict) else None
        packet_id = str(
            (entry_row or {}).get("packet_id")
            or (entry_intent or {}).get("packet_id")
            or ""
        )
        if not packet_id:
            for row in related_decisions:
                packet_id = str(row.get("packet_id") or "")
                if packet_id:
                    break

        market_path = collect_market_path(frames_root, entry, exit_time)

        evidence.append(
            {
                "outcome": outcome,
                "outcome_execution": outcome_execution_summary(outcome),
                "entry_decision": entry_intent,
                "related_decisions": related_decisions,
                "delivery_receipt": receipts_by_packet.get(packet_id),
                "market_path": market_path,
            }
        )
    for row in evidence:
        execution = row.get("outcome_execution")
        if not isinstance(execution, dict):
            execution = {}
        facts = debrief_facts(
            row["outcome"],
            execution,
            row.get("entry_decision") if isinstance(row.get("entry_decision"), dict) else None,
        )
        row["facts"] = facts
        row["facts_sha256"] = stable_facts_sha256(facts)
    return evidence
