"""NT parity helpers adapted for Glitch Topstep Hermes profile."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from distribution_manifest import PROMPT_VERSION
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
    {"started", "failed", "execution_failed", "delivery_incomplete"}
)


def wake_trigger_path(supervisor: Path) -> Path:
    return supervisor / "active-wake-triggers.json"


def validate_wake_triggers(triggers: Any) -> None:
    if not isinstance(triggers, list):
        raise ValueError("wake_triggers_invalid")
    for trigger_index, trigger in enumerate(triggers):
        if not isinstance(trigger, dict):
            raise ValueError(f"wake_trigger_invalid:{trigger_index}")
        if set(trigger) != {"type", "direction", "price"}:
            raise ValueError(f"wake_trigger_fields_invalid:{trigger_index}")
        if trigger.get("type") != "PRICE_CROSS":
            raise ValueError(f"wake_trigger_type_invalid:{trigger_index}")
        if trigger.get("direction") not in {"ABOVE", "BELOW"}:
            raise ValueError(f"wake_trigger_direction_invalid:{trigger_index}")
        price = trigger.get("price")
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(float(price))
        ):
            raise ValueError(f"wake_trigger_price_invalid:{trigger_index}")


def explicit_price_crosses(condition: str) -> set[tuple[str, float]]:
    pattern = re.compile(
        r"\b(above|over|below|under)\s+([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    crosses: set[tuple[str, float]] = set()
    for match in pattern.finditer(condition):
        direction = "ABOVE" if match.group(1).lower() in {"above", "over"} else "BELOW"
        crosses.add((direction, float(match.group(2))))
    return crosses


def require_explicit_wake_triggers(
    audit: dict[str, Any],
    triggers: list[dict[str, Any]],
) -> None:
    expected = explicit_price_crosses(str(audit.get("change_condition", "")))
    actual = {
        (str(trigger.get("direction")), float(trigger.get("price")))
        for trigger in triggers
    }
    missing = sorted(expected.difference(actual))
    if missing:
        raise ValueError(f"wake_triggers_missing_for_change_condition:{missing}")


def packet_current_price(packet: dict[str, Any]) -> float | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    value = market.get("last")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def packet_one_minute_range(packet: dict[str, Any]) -> tuple[float, float] | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    try:
        close = float(market["last"])
        high = float(market.get("high", close))
        low = float(market.get("low", close))
    except (KeyError, TypeError, ValueError):
        return None
    return low, high


def prior_frame_price(state: Path, packet: dict[str, Any]) -> float | None:
    frames_dir = state / "minute-frames"
    if not frames_dir.is_dir():
        return None
    current_id = parse_utc(packet["created_utc"]).strftime("%Y%m%dT%H%MZ")
    for path in sorted(frames_dir.glob("*.json"), reverse=True):
        if path.stem >= current_id:
            continue
        frame = read_optional_json(path)
        if not frame:
            continue
        prior_packet = frame.get("packet")
        if isinstance(prior_packet, dict):
            price = packet_current_price(prior_packet)
            if price is not None:
                return price
    return None


def wake_trigger_fired(state: Path, packet: dict[str, Any]) -> bool:
    path = wake_trigger_path(state / "supervisor")
    if not path.is_file():
        return False
    try:
        trigger_state = read_json(path)
    except (OSError, ValueError, TypeError):
        return False
    triggers = trigger_state.get("triggers")
    if not isinstance(triggers, list):
        return False
    previous = prior_frame_price(state, packet)
    current = packet_current_price(packet)
    current_range = packet_one_minute_range(packet)
    if previous is None or current is None:
        return False
    current_low, current_high = current_range or (current, current)
    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue
        try:
            level = float(trigger["price"])
        except (KeyError, TypeError, ValueError):
            continue
        direction = trigger.get("direction")
        if direction == "ABOVE" and previous <= level < max(current, current_high):
            return True
        if direction == "BELOW" and previous >= level > min(current, current_low):
            return True
    return False


def persist_wake_triggers(state: Path, intent: dict[str, Any], packet_id: str) -> None:
    triggers = intent.get("wake_triggers")
    if not isinstance(triggers, list):
        triggers = []
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        wake_trigger_path(supervisor),
        {
            "schema_version": "glitch.topstep.wake_triggers.v1",
            "packet_id": packet_id,
            "triggers": triggers,
            "updated_utc": utc_now(),
        },
    )


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


def flat_outside_session_window(
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
) -> bool:
    if not respect_session_gate_enabled() or session_gate_override_enabled():
        return False
    if directive is not None or packet_positioned(packet):
        return False
    return packet_session_closed(packet)


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
    if not any(
        compact.get(key) is not None
        for key in ("http_status", "status", "code")
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
            preserve_change_condition=index == len(decisions) - 1,
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


def classify_delivery_result(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "transport_uncertain"
    if result.get("transport_error"):
        return "transport_uncertain"
    status = result.get("http_status")
    if not isinstance(status, int):
        return "transport_uncertain"
    if status in {408, 425, 429} or status >= 500:
        return "transport_uncertain"
    if isinstance(result.get("body"), dict):
        body = result["body"]
        if body.get("code") in {
            "intent_delivery_unreconciled",
            "intent_already_processing_or_recovery_required",
        }:
            return "transport_uncertain"
    if status >= 400:
        return "terminal_rejection"
    body = result.get("body")
    if isinstance(body, dict):
        executor = body.get("executor")
        executor_code = body.get("executor_code")
        if executor == "failed":
            return "terminal_rejection"
        if executor == "skipped" and executor_code != "no_op_action":
            return "terminal_rejection"
        if executor == "pending":
            return "transport_uncertain"
    return "successful"


GATEWAY_COGNITIVE_REJECTION_CODES = frozenset({
    "stop_would_widen",
    "target_would_widen",
    "stop_wrong_side_of_market",
    "target_wrong_side_of_entry",
    "move_stop_unavailable",
    "protection_not_proven",
    "action_not_supported_in_current_packet",
    "position_already_flat",
    "position_not_found",
    "target_tranche_not_found",
    "target_tranche_already_flat",
    "exit_quantity_exceeds_tranche_remaining",
    "exit_quantity_exceeds_attributable_remaining",
    "exit_quantity_invalid",
    "target_intent_id_required",
    "protective_leg_unresolved",
    "position_side_unknown",
    "amendment_current_price_missing",
    "amendment_market_reference_missing",
    "amendment_entry_reference_missing",
    "no_execution_action",
})

GATEWAY_SYSTEM_DEFECT_CODES = frozenset({
    "intent_schema_invalid",
    "intent_delivery_unreconciled",
    "intent_already_processing_or_recovery_required",
    "intent_body_conflict",
    "projectx_mutation_rejected",
    "projectx_mutation_outcome_ambiguous",
    "protection_cancel_failed",
    "decision_packet_unknown_or_expired",
    "action_not_implemented",
    "trading_disabled_by_operator",
    "account_name_mismatch",
    "snapshot_hash_mismatch",
})


def classify_gateway_rejection(result: dict[str, Any]) -> str | None:
    if classify_delivery_result(result) != "terminal_rejection":
        return None
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    code = str(body.get("code") or body.get("executor_code") or "")
    if code in GATEWAY_COGNITIVE_REJECTION_CODES:
        return "cognitive_rejection"
    if code in GATEWAY_SYSTEM_DEFECT_CODES:
        return "system_defect"
    http_status = result.get("http_status")
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return "cognitive_rejection"
    return "system_defect"


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
    )
    summary = {key: outcome.get(key) for key in keys if key in outcome}
    attribution = outcome.get("attribution")
    if isinstance(attribution, dict) and attribution.get("protection_status"):
        summary["protection_status"] = attribution["protection_status"]
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
    }


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


def is_registered_delivery_conflict(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    body = result.get("body")
    return isinstance(body, dict) and body.get("code") == "intent_body_conflict"


def delivery_wire_path(state: Path, packet_id: str) -> Path:
    return state / "delivery-wire" / f"{packet_id}.json"


def load_delivery_wire(state: Path, packet_id: str) -> dict[str, Any] | None:
    payload = read_optional_json(delivery_wire_path(state, packet_id))
    if not isinstance(payload, dict):
        return None
    wire = payload.get("wire")
    return wire if isinstance(wire, dict) else None


def save_delivery_wire(state: Path, packet_id: str, wire: dict[str, Any]) -> None:
    delivery_wire_path(state, packet_id).parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        delivery_wire_path(state, packet_id),
        {
            "schema_version": "glitch.topstep.delivery_wire.v1",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": str(wire.get("intent_id") or ""),
            "wire": wire,
        },
    )


def clear_delivery_wire(state: Path, packet_id: str) -> None:
    try:
        delivery_wire_path(state, packet_id).unlink(missing_ok=True)
    except OSError:
        pass


def reconcile_registered_delivery(
    intent_id: str,
    packet_id: str,
    state: Path,
    post_intent: Callable[[dict[str, Any]], dict[str, Any]],
    fetch_receipt: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    wire = load_delivery_wire(state, packet_id)
    if wire is not None:
        retry = post_intent(wire)
        if not is_registered_delivery_conflict(retry):
            return retry
    if fetch_receipt is not None and intent_id:
        receipt = fetch_receipt(intent_id)
        if isinstance(receipt, dict):
            return {"http_status": 200, "body": receipt}
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "intent_delivery_unreconciled",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": intent_id,
        },
    )
    return {
        "http_status": 503,
        "body": {
            "code": "intent_delivery_unreconciled",
            "intent_id": intent_id,
        },
    }


def deliver_packet_intent(
    state: Path,
    packet_id: str,
    intent: dict[str, Any],
    directive: dict[str, Any] | None,
    post_intent: Callable[[dict[str, Any]], dict[str, Any]],
    prepare_intent_for_delivery: Callable[
        [dict[str, Any], dict[str, Any] | None],
        dict[str, Any],
    ],
    fetch_receipt: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """POST /intent with frozen wire identity across transport-uncertain retries."""
    wire = load_delivery_wire(state, packet_id)
    if wire is None:
        wire = prepare_intent_for_delivery(intent, directive)
        save_delivery_wire(state, packet_id, wire)
    result = post_intent(wire)
    if is_registered_delivery_conflict(result):
        result = reconcile_registered_delivery(
            str(intent.get("intent_id") or ""),
            packet_id,
            state,
            post_intent,
            fetch_receipt,
        )
    return result


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


def pending_outbox(state: Path) -> tuple[str, Path] | None:
    outbox_dir = state / "outbox"
    if not outbox_dir.is_dir():
        return None
    for path in sorted(outbox_dir.glob("*.json")):
        receipt_path = state / "receipts" / f"{path.stem}.json"
        if not receipt_path.is_file():
            return path.stem, path
        receipt = read_optional_json(receipt_path)
        if isinstance(receipt, dict) and classify_delivery_result(
            receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        ) == "transport_uncertain":
            return path.stem, path
    return None


def intent_is_entry(intent: dict[str, Any]) -> bool:
    return str(intent.get("action") or "") in {"ENTER_LONG", "ENTER_SHORT"}


def _minute_frames_dir(state_or_frames_root: Path) -> Path:
    nested = state_or_frames_root / "minute-frames"
    if nested.is_dir():
        return nested
    return state_or_frames_root


def frame_for_packet_id(state_or_frames_root: Path, packet_id: str) -> dict[str, Any] | None:
    # ponytail: O(n) scan over minute-frames; fine at typical retention sizes
    frames_dir = _minute_frames_dir(state_or_frames_root)
    if not frames_dir.is_dir():
        return None
    for path in sorted(frames_dir.glob("*.json")):
        frame = read_optional_json(path)
        if not isinstance(frame, dict):
            continue
        packet = frame.get("packet")
        if isinstance(packet, dict) and str(packet.get("packet_id") or "") == packet_id:
            return frame
    return None


def packet_for_outbox_id(state: Path, packet_id: str) -> dict[str, Any] | None:
    frame = frame_for_packet_id(state, packet_id)
    if frame is None:
        return None
    packet = frame.get("packet")
    return packet if isinstance(packet, dict) else None


def prune_delivered_outboxes(state: Path) -> int:
    outbox_dir = state / "outbox"
    if not outbox_dir.is_dir():
        return 0
    pruned = 0
    for path in outbox_dir.glob("*.json"):
        receipt_path = state / "receipts" / f"{path.stem}.json"
        if not receipt_path.is_file():
            continue
        receipt = read_optional_json(receipt_path)
        if not isinstance(receipt, dict):
            continue
        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        if classify_delivery_result(result) == "transport_uncertain":
            continue
        try:
            path.unlink(missing_ok=True)
            pruned += 1
        except OSError:
            continue
    return pruned


def discard_stale_outbox_intent(
    state: Path,
    outbox_path: Path,
    packet_id: str,
    intent: dict[str, Any],
    *,
    token: str,
) -> bool:
    """Discard only when the decision packet was never captured locally.

    A newer gateway packet id must not invalidate a completed decision: delivery
    realigns snapshot_hash against the current packet before POST /intent.
    """
    del token  # retained for call-site compatibility
    reason: str | None = None
    if packet_for_outbox_id(state, packet_id) is None:
        reason = "stored_packet_not_found"
    if reason is None:
        return False
    try:
        outbox_path.unlink(missing_ok=True)
    except OSError:
        return False
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "intent_discarded_stale_packet",
            "reason": reason,
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "action": str(intent.get("action") or ""),
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

        entry_intent = next(
            (
                row.get("intent")
                for row in decisions
                if isinstance(row.get("intent"), dict)
                and str(row["intent"].get("intent_id") or "") == intent_id
            ),
            None,
        )
        packet_id = str((entry_intent or {}).get("packet_id") or "")
        if not packet_id:
            for row in related_decisions:
                packet_id = str(row.get("packet_id") or "")
                if packet_id:
                    break

        market_path: list[dict[str, Any]] = []
        if packet_id:
            start_collecting = False
            for path in sorted(frames_root.glob("*.json")):
                frame = read_optional_json(path)
                if not frame:
                    continue
                if path.stem == packet_id:
                    start_collecting = True
                if not start_collecting:
                    continue
                packet = frame.get("packet")
                market = packet.get("market") if isinstance(packet, dict) else {}
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
                if parse_utc(outcome["exit_utc"]) <= parse_utc(
                    (packet or {}).get("created_utc", outcome["exit_utc"])
                ):
                    break

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
