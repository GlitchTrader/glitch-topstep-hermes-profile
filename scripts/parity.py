"""NT parity helpers adapted for Glitch Topstep Hermes profile."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    }


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
                "entry_decision": entry_intent,
                "related_decisions": related_decisions,
                "delivery_receipt": receipts_by_packet.get(packet_id),
                "market_path": market_path,
            }
        )
    return evidence
