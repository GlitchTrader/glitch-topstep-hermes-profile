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
from workflows.debrief_evidence import (
    collect_market_path,
    debrief_evidence,
    debrief_facts,
    debrief_prompt_evidence,
    outcome_execution_summary,
    stable_facts_sha256,
)
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

from workflows.cycle_context import (
    CURRENT_GUIDANCE_SCHEMA,
    CURRENT_PLAN_SCHEMA,
    FULL_CHANGE_CONDITION_TAIL,
    RETRYABLE_ATTEMPT_STATUSES,
    apply_cognitive_overlay,
    compact_cycle_ledger_context,
    compact_decision_row,
    compact_outcome_row,
    compact_receipt_row,
    compute_cycle_evidence_delta,
    invocation_reason,
    last_evidence_exists,
    latest_prior_attempt,
    learning_context,
    monitor_should_launch_cycle,
    read_trading_learning_artifact,
    repeated_change_condition_warning,
    resolve_cycle_invocation,
    summarize_outcomes_for_cycle,
    summarized_outcome_backed_lessons,
)
from workflows.session_gates import (
    flat_outside_session_window,
    market_quiescence_gate_enabled,
    market_quiescent_skip_details,
    market_quiescent_skip_reason,
    max_quiescent_trade_count_60s,
    packet_positioned,
    packet_quote_age_ms,
    packet_quote_stale,
    packet_raw_quote_age_ms,
    packet_reconnect_pending,
    packet_session_closed,
    packet_session_phase,
    packet_stream_health,
    packet_trade_count_60s,
    quote_age_observation,
    respect_session_gate_enabled,
    session_gate_override_enabled,
    session_maintenance_skip_details,
    stale_gateway_skip_reason,
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
    "entry_geometry_invalid_at_latest_price",
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
    """Discard entry outbox when live executable geometry no longer fits stop/target.

    Pending outbox retries validate against the stored decision packet, then
    prepare_intent_for_delivery re-checks executable geometry on the fresh quote.
    Superseded entries are dropped once so the next cycle performs one fresh
    comparison; cognitive entry bands are never widened.
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
    entry_min = intent.get("entry_price_min")
    entry_max = intent.get("entry_price_max")
    entry_width = None
    if isinstance(entry_min, (int, float)) and not isinstance(entry_min, bool):
        if isinstance(entry_max, (int, float)) and not isinstance(entry_max, bool):
            entry_width = float(entry_max) - float(entry_min)
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
            "entry_price_min": entry_min,
            "entry_price_max": entry_max,
            "entry_width": entry_width,
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

