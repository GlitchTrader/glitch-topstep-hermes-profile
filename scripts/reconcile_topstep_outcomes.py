"""Reconcile gateway trade outcomes with Hermes decision and receipt evidence."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from common import read_jsonl, read_optional_json, utc_now

OUTCOME_SCHEMA = "glitch.topstep.trade_outcome.v1"
CANONICAL_SCHEMA = "glitch.topstep.trade_outcome_canonical.v1"

COGNITIVE_FIREWALL_REJECTIONS = {
    "action_not_available",
    "entry_not_eligible",
    "entry_quantity_invalid",
    "positioned_entry_not_supported",
    "long_geometry_invalid",
    "short_geometry_invalid",
    "move_stop_must_tighten_long",
    "move_stop_must_tighten_short",
    "move_stop_current_unknown",
    "forced_entry_not_honored",
    "daily_loss_limit",
    "max_contracts",
}

SYSTEM_REJECTION_PREFIXES = (
    "gateway_",
    "hermes_failed",
    "telegram_",
    "transport_",
)


def outcomes_raw_path(root: Path) -> Path:
    configured = os.environ.get("GLITCH_TOPSTEP_OUTCOMES_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return root / "state" / "outcomes.jsonl"


def outcomes_canonical_path(root: Path) -> Path:
    return root / "state" / "supervisor" / "canonical-outcomes.jsonl"


def _intent_index(state: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in (state / "outbox").glob("*.json"):
        value = read_optional_json(path)
        if value and value.get("intent_id"):
            index[str(value["intent_id"])] = {
                "intent": value,
                "packet_id": path.stem,
                "source": "outbox",
            }
    for row in read_jsonl(state / "decisions.jsonl"):
        intent = row.get("intent")
        if not isinstance(intent, dict) or not intent.get("intent_id"):
            continue
        intent_id = str(intent["intent_id"])
        index[intent_id] = {
            "intent": intent,
            "packet_id": str(row.get("packet_id") or ""),
            "recorded_utc": row.get("recorded_utc"),
            "source": "decisions",
        }
    return index


def _receipt_index(state: Path) -> dict[str, dict[str, Any]]:
    by_intent: dict[str, dict[str, Any]] = {}
    by_packet: dict[str, dict[str, Any]] = {}
    for path in (state / "receipts").glob("*.json"):
        value = read_optional_json(path)
        if not value:
            continue
        packet_id = path.stem
        by_packet[packet_id] = value
        intent_id = str(value.get("intent_id") or "")
        if intent_id:
            by_intent[intent_id] = value
    for row in read_jsonl(state / "receipts.jsonl"):
        intent_id = str(row.get("intent_id") or "")
        packet_id = str(row.get("packet_id") or "")
        if intent_id:
            by_intent[intent_id] = row
        if packet_id:
            by_packet[packet_id] = row
    return {"by_intent": by_intent, "by_packet": by_packet}


def _receipt_shadow_only(receipt: dict[str, Any] | None) -> bool:
    if not receipt:
        return True
    result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    if body.get("shadow_only") is True:
        return True
    if str(body.get("trading_mode") or "").lower() == "shadow":
        return True
    return False


def _attempt_error(state: Path, packet_id: str) -> str | None:
    attempt = read_optional_json(state / "attempts" / f"{packet_id}.json")
    if not attempt:
        return None
    error = str(attempt.get("error") or "")
    return error or None


def classify_rejection(error: str | None) -> str | None:
    if not error:
        return None
    lowered = error.lower()
    for code in COGNITIVE_FIREWALL_REJECTIONS:
        if code in lowered:
            return code
    if lowered.startswith(SYSTEM_REJECTION_PREFIXES):
        return "system_defect"
    if "validation" in lowered or "invalid" in lowered:
        return "validation_rejection"
    return None


def enrich_outcome(
    raw: dict[str, Any],
    *,
    intent_index: dict[str, dict[str, Any]],
    receipt_index: dict[str, dict[str, dict[str, Any]]],
    state: Path,
) -> dict[str, Any]:
    intent_id = str(raw.get("intent_id") or "")
    context = intent_index.get(intent_id, {})
    intent = context.get("intent") if isinstance(context.get("intent"), dict) else {}
    packet_id = str(context.get("packet_id") or "")
    receipt = receipt_index["by_intent"].get(intent_id) or receipt_index["by_packet"].get(packet_id)
    attempt_error = _attempt_error(state, packet_id) if packet_id else None
    rejection_code = classify_rejection(attempt_error)
    shadow_only = _receipt_shadow_only(receipt)
    learning_eligible = (
        raw.get("learning_eligible") is True
        and not shadow_only
        and rejection_code not in COGNITIVE_FIREWALL_REJECTIONS
        and rejection_code != "system_defect"
    )
    net_pnl = float(raw.get("realized_pnl_usd") or 0) - float(raw.get("fees_usd") or 0)
    return {
        "schema_version": CANONICAL_SCHEMA,
        "outcome_id": raw.get("outcome_id"),
        "intent_id": intent_id,
        "account": raw.get("account"),
        "instrument": raw.get("instrument"),
        "action": intent.get("action"),
        "entry_utc": raw.get("entry_utc") or context.get("recorded_utc"),
        "exit_utc": raw.get("exit_utc"),
        "realized_pnl_usd": raw.get("realized_pnl_usd"),
        "fees_usd": raw.get("fees_usd"),
        "net_pnl_usd": round(net_pnl, 2),
        "learning_eligible": learning_eligible,
        "shadow_only": shadow_only,
        "packet_id": packet_id or None,
        "rejection_code": rejection_code,
        "intent": {
            "quantity": intent.get("quantity"),
            "stop_loss": intent.get("stop_loss"),
            "take_profit_1": intent.get("take_profit_1"),
            "confidence": intent.get("confidence"),
        },
        "evidence": raw.get("evidence"),
        "reconciled_utc": utc_now(),
    }


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def reconcile_outcomes(root: Path) -> dict[str, Any]:
    state = root / "state"
    raw_path = outcomes_raw_path(root)
    canonical_path = outcomes_canonical_path(root)
    prior = {str(row.get("outcome_id")): row for row in read_jsonl(canonical_path) if row.get("outcome_id")}
    raw_rows = [
        row for row in read_jsonl(raw_path)
        if row.get("schema_version") == OUTCOME_SCHEMA and row.get("outcome_id")
    ]
    intent_index = _intent_index(state)
    receipt_index = _receipt_index(state)
    canonical_rows = [
        enrich_outcome(row, intent_index=intent_index, receipt_index=receipt_index, state=state)
        for row in raw_rows
    ]
    canonical_rows.sort(key=lambda row: str(row.get("exit_utc") or ""))
    write_jsonl_atomic(canonical_path, canonical_rows)
    new_ids = [
        str(row["outcome_id"])
        for row in canonical_rows
        if str(row["outcome_id"]) not in prior
    ]
    return {
        "raw_count": len(raw_rows),
        "canonical_count": len(canonical_rows),
        "new_outcome_ids": new_ids,
        "canonical_path": str(canonical_path),
    }


def main() -> int:
    from common import configure_environment

    root = configure_environment()
    result = reconcile_outcomes(root)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
