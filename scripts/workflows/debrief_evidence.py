"""Debrief evidence assembly — extracted from parity (audit C1)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from common import parse_utc, read_jsonl, read_optional_json
from selection_ev import fill_observability, selection_ev_arithmetic_audit


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
    """Collect minute-frame last/high/low between entry and exit (inclusive)."""
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
        prompt_row = {
            "facts": row["facts"],
            "facts_sha256": row["facts_sha256"],
            "entry_decision": row.get("entry_decision"),
            "market_path": row.get("market_path"),
            "related_decision_count": len(row.get("related_decisions") or []),
        }
        if isinstance(row.get("selection_ev_arithmetic"), dict):
            prompt_row["selection_ev_arithmetic"] = row["selection_ev_arithmetic"]
        if isinstance(row.get("fill_observability"), dict):
            prompt_row["fill_observability"] = row["fill_observability"]
        prompt_rows.append(prompt_row)
    return prompt_rows


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

        entry_decision = entry_intent if isinstance(entry_intent, dict) else None
        evidence.append(
            {
                "outcome": outcome,
                "outcome_execution": outcome_execution_summary(outcome),
                "entry_decision": entry_decision,
                "related_decisions": related_decisions,
                "delivery_receipt": receipts_by_packet.get(packet_id),
                "market_path": market_path,
                "selection_ev_arithmetic": selection_ev_arithmetic_audit(
                    entry_decision.get("decision_audit") if entry_decision else None,
                    entry_decision.get("forecast") if entry_decision else None,
                ),
                "fill_observability": fill_observability(entry_decision, outcome),
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
