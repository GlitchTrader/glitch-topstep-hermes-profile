"""Direct-cycle invocation resolution and cognition prompt context."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from common import parse_utc, read_json, read_jsonl, read_optional_json
from distribution_manifest import PROMPT_VERSION
from workflows.session_gates import flat_outside_session_window
from workflows.wake_triggers import (
    evaluate_wake_triggers,
    order_flow_window,
    packet_current_price,
    read_pending_wake_invocation,
    wake_trigger_fired,
)

CURRENT_PLAN_SCHEMA = "glitch.topstep.portfolio_plan.v1"
CURRENT_GUIDANCE_SCHEMA = "glitch.topstep.guidance.v1"
RETRYABLE_ATTEMPT_STATUSES = frozenset(
    {"failed", "execution_failed", "delivery_incomplete"}
)
FULL_CHANGE_CONDITION_TAIL = 2


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


def resolve_cycle_invocation(
    state: Path,
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
    *,
    flat_decision_interval_minutes: int,
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve one direct-cycle invocation: wake first, held rescan fallback, then scheduled."""
    from trigger_lifecycle import (
        comparison_wake_detail,
        evaluate_comparison_triggers,
        pending_held_rescan_reason,
    )

    packet_id = str(packet.get("packet_id") or "")
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    is_positioned = int(account.get("instrument_open_contracts") or 0) != 0

    if directive is not None:
        return "operator_directive", None
    if is_positioned:
        return "positioned", None

    pending_wake = read_pending_wake_invocation(state)
    if pending_wake:
        return "condition_change", {
            "wake_reason": pending_wake.get("wake_reason"),
            "wake_trigger": pending_wake.get("wake_trigger"),
            "trigger_key": pending_wake.get("trigger_key"),
        }

    comparison_fired = evaluate_comparison_triggers(state, packet)
    if comparison_fired:
        return "condition_change", comparison_wake_detail(comparison_fired[0])

    wake_detail = evaluate_wake_triggers(state, packet)
    if wake_detail:
        return "condition_change", wake_detail

    if flat_outside_session_window(packet, directive):
        return None, None

    held = pending_held_rescan_reason(
        state,
        packet,
        flat_decision_interval_minutes=flat_decision_interval_minutes,
    )
    if held:
        return held, None

    if not last_evidence_exists(state):
        return "first_packet", None
    prior = latest_prior_attempt(state, packet_id)
    if prior is not None and prior.get("status") in RETRYABLE_ATTEMPT_STATUSES:
        return "retry_after_failure", None
    minute = parse_utc(packet["created_utc"]).minute
    if minute % flat_decision_interval_minutes == 0:
        return "scheduled", None
    return None, None


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
