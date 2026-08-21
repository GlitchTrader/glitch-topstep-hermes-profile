"""Runtime lifecycle for multi-instrument comparison triggers (GTHP-TRIGGER-01)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import parse_utc, read_optional_json, utc_now, write_json_atomic
from scanner_contract import MARKER, TRIGGER_STATUSES, parse_comparison_line


SCHEMA_VERSION = "glitch.topstep.comparison_triggers.v1"
PENDING_HELD_SCHEMA = "glitch.topstep.pending_held_rescan.v1"
# ponytail: retain last N EXPIRED rows only; active HELD/FAILED are never dropped here.
EXPIRED_TRIGGER_RETENTION = 100


def comparison_trigger_path(supervisor: Path) -> Path:
    return supervisor / "active-comparison-triggers.json"


def pending_held_rescan_path(supervisor: Path) -> Path:
    return supervisor / "pending-held-rescan.json"


def _next_flat_slot_utc(moment: datetime, interval_minutes: int) -> datetime:
    interval = max(1, interval_minutes)
    base = moment.astimezone(timezone.utc).replace(second=0, microsecond=0)
    slot_minute = (base.minute // interval + 1) * interval
    if slot_minute >= 60:
        hour_carry = slot_minute // 60
        return base.replace(minute=0) + timedelta(hours=hour_carry)
    return base.replace(minute=slot_minute)


def parse_comparison_ledger(intent: dict[str, Any]) -> dict[str, Any] | None:
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    text = audit.get("decisive_evidence")
    if not isinstance(text, str):
        return None
    stripped = text.lstrip()
    if not stripped.startswith(MARKER):
        return None
    if stripped.startswith("INSTRUMENT_COMPARISON_V1:"):
        raise ValueError("instrument_comparison_legacy_json")
    return parse_comparison_line(
        text,
        packet_id=str(intent.get("packet_id") or ""),
        expires_utc=str(intent.get("expires_utc") or ""),
    )


def _trigger_map(document: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not document:
        return {}
    rows = document.get("triggers")
    if not isinstance(rows, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("trigger_id"), str):
            mapped[row["trigger_id"]] = row
    return mapped


def merge_comparison_triggers(
    prior: dict[str, dict[str, Any]],
    ledger: dict[str, Any],
    *,
    packet_id: str,
) -> dict[str, dict[str, Any]]:
    merged = dict(prior)
    for candidate in ledger.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        instrument = str(candidate.get("instrument") or "").upper()
        triggers = candidate.get("triggers")
        if not isinstance(triggers, list):
            continue
        for trigger in triggers:
            if not isinstance(trigger, dict):
                continue
            trigger_id = str(trigger.get("trigger_id") or "")
            if not trigger_id:
                raise ValueError("instrument_trigger_invalid")
            status = trigger.get("status")
            if status not in TRIGGER_STATUSES:
                raise ValueError("instrument_trigger_status_invalid")
            if trigger.get("source_packet_id") != packet_id:
                raise ValueError("instrument_trigger_source_mismatch")
            previous = merged.get(trigger_id)
            if previous is not None:
                if previous.get("condition") != trigger.get("condition") and previous.get("status") == status:
                    raise ValueError("comparison_trigger_ratchet_detected")
            merged[trigger_id] = {
                **trigger,
                "instrument": instrument,
                "updated_utc": utc_now(),
            }
    return merged


def _ledger_instruments(ledger: dict[str, Any]) -> set[str]:
    instruments: set[str] = set()
    for candidate in ledger.get("candidates") or []:
        if isinstance(candidate, dict):
            instrument = str(candidate.get("instrument") or "").upper()
            if instrument:
                instruments.add(instrument)
    return instruments


def _trigger_expired(trigger: dict[str, Any], now: datetime) -> bool:
    raw = trigger.get("expires_utc")
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        return parse_utc(raw) <= now
    except (TypeError, ValueError):
        return True


def _has_active_held(rows: Any, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "HELD":
            continue
        if _trigger_expired(row, current):
            continue
        return True
    return False


def _compact_expired_triggers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [row for row in rows if row.get("status") != "EXPIRED"]
    expired = [row for row in rows if row.get("status") == "EXPIRED"]
    expired.sort(key=lambda row: str(row.get("updated_utc") or ""), reverse=True)
    return active + expired[:EXPIRED_TRIGGER_RETENTION]


def reconcile_comparison_triggers(
    merged: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    ledger: dict[str, Any] | None = None,
    packet_id: str | None = None,
) -> None:
    """Expire stale HELD at runtime and supersede prior-instrument watches."""
    current = now or datetime.now(timezone.utc)
    for row in merged.values():
        if row.get("status") == "HELD" and _trigger_expired(row, current):
            row["status"] = "EXPIRED"
            row["updated_utc"] = utc_now()

    if ledger is not None and packet_id:
        instruments = _ledger_instruments(ledger)
        for row in merged.values():
            if row.get("status") != "HELD" or _trigger_expired(row, current):
                continue
            instrument = str(row.get("instrument") or "").upper()
            if instrument not in instruments:
                row["status"] = "EXPIRED"
                row["updated_utc"] = utc_now()
                continue
            if row.get("source_packet_id") != packet_id:
                row["status"] = "EXPIRED"
                row["updated_utc"] = utc_now()


def _write_trigger_document(
    state: Path,
    merged: dict[str, dict[str, Any]],
    *,
    packet_id: str | None = None,
) -> list[dict[str, Any]]:
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    prior_doc = read_optional_json(comparison_trigger_path(supervisor))
    triggers = _compact_expired_triggers(list(merged.values()))
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "updated_utc": utc_now(),
        "triggers": triggers,
    }
    if packet_id:
        document["packet_id"] = packet_id
    elif isinstance(prior_doc, dict) and prior_doc.get("packet_id"):
        document["packet_id"] = prior_doc.get("packet_id")
    if isinstance(prior_doc, dict) and isinstance(prior_doc.get("eval_snapshot"), dict):
        document["eval_snapshot"] = prior_doc["eval_snapshot"]
    write_json_atomic(comparison_trigger_path(supervisor), document)
    return triggers


def load_reconciled_trigger_map(
    state: Path,
    *,
    ledger: dict[str, Any] | None = None,
    packet_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    supervisor = state / "supervisor"
    document = read_optional_json(comparison_trigger_path(supervisor))
    merged = _trigger_map(document)
    reconcile_comparison_triggers(merged, ledger=ledger, packet_id=packet_id)
    _write_trigger_document(state, merged, packet_id=packet_id or (document or {}).get("packet_id"))
    return merged


def active_held_triggers(state: Path) -> list[dict[str, Any]]:
    merged = load_reconciled_trigger_map(state)
    now = datetime.now(timezone.utc)
    return [
        row
        for row in merged.values()
        if isinstance(row, dict)
        and row.get("status") == "HELD"
        and not _trigger_expired(row, now)
    ]


def trigger_review_mode(
    invocation_reason: str | None,
    wake_detail: dict[str, Any] | None,
) -> bool:
    if invocation_reason == "held_rescan":
        return True
    if invocation_reason != "condition_change" or not isinstance(wake_detail, dict):
        return False
    trigger = wake_detail.get("wake_trigger")
    return isinstance(trigger, dict) and trigger.get("type") == "COMPARISON_TRIGGER"


def persist_comparison_triggers(
    state: Path,
    intent: dict[str, Any],
    packet_id: str,
    *,
    flat_decision_interval_minutes: int = 5,
) -> None:
    ledger = parse_comparison_ledger(intent)
    if ledger is None:
        return
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    prior_doc = read_optional_json(comparison_trigger_path(supervisor))
    merged = merge_comparison_triggers(_trigger_map(prior_doc), ledger, packet_id=packet_id)
    reconcile_comparison_triggers(merged, ledger=ledger, packet_id=packet_id)
    triggers = _write_trigger_document(state, merged, packet_id=packet_id)
    if str(intent.get("action") or "").upper() == "NOTHING" and _has_active_held(triggers):
        created_raw = intent.get("created_utc") or utc_now()
        created = parse_utc(str(created_raw))
        write_json_atomic(
            pending_held_rescan_path(supervisor),
            {
                "schema_version": PENDING_HELD_SCHEMA,
                "recorded_utc": utc_now(),
                "source_packet_id": packet_id,
                "due_minute_utc": created_raw,
                "earliest_rescan_utc": _next_flat_slot_utc(
                    created,
                    flat_decision_interval_minutes,
                )
                .isoformat()
                .replace("+00:00", "Z"),
                "reason": "held_trigger_requires_rescan",
            },
        )


def pending_held_rescan_reason(
    state: Path,
    packet: dict[str, Any] | None = None,
    *,
    flat_decision_interval_minutes: int = 5,
) -> str | None:
    supervisor = state / "supervisor"
    pending = read_optional_json(pending_held_rescan_path(supervisor))
    if not pending:
        return None
    merged = load_reconciled_trigger_map(state)
    if not _has_active_held(merged.values()):
        consume_pending_held_rescan(state)
        return None
    if isinstance(packet, dict) and packet.get("created_utc"):
        earliest_raw = pending.get("earliest_rescan_utc")
        if isinstance(earliest_raw, str) and earliest_raw.strip():
            if parse_utc(packet["created_utc"]) < parse_utc(earliest_raw):
                return None
        minute = parse_utc(packet["created_utc"]).minute
        if minute % max(1, flat_decision_interval_minutes) != 0:
            return None
    return "held_rescan"


def consume_pending_held_rescan(state: Path) -> None:
    pending_held_rescan_path(state / "supervisor").unlink(missing_ok=True)


_CONDITION_LEVEL = re.compile(
    r"(?i)\b(cross|above|below)\b[^0-9.-]*([0-9]+(?:\.[0-9]+)?)"
)


def _packet_price(packet: dict[str, Any]) -> float | None:
    market = packet.get("market")
    if not isinstance(market, dict):
        return None
    for key in ("last", "bid", "ask"):
        value = market.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _parse_condition_level(condition: str) -> tuple[str, float] | None:
    match = _CONDITION_LEVEL.search(str(condition or ""))
    if not match:
        return None
    return match.group(1).lower(), float(match.group(2))


def _trigger_condition_met(
    trigger: dict[str, Any],
    packet: dict[str, Any],
    *,
    prior_price: float | None,
) -> bool:
    parsed = _parse_condition_level(str(trigger.get("condition") or ""))
    current = _packet_price(packet)
    if parsed is None or current is None:
        return False
    mode, level = parsed
    if mode == "above":
        return current > level
    if mode == "below":
        return current < level
    if prior_price is None:
        return False
    return prior_price <= level < current or prior_price >= level > current


def _comparison_eval_snapshot(document: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {}
    snapshot = document.get("eval_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def update_comparison_eval_snapshot(state: Path, packet: dict[str, Any]) -> None:
    supervisor = state / "supervisor"
    path = comparison_trigger_path(supervisor)
    document = read_optional_json(path)
    if not isinstance(document, dict):
        return
    price = _packet_price(packet)
    snapshot = _comparison_eval_snapshot(document)
    if price is not None:
        snapshot["price"] = price
    snapshot["packet_id"] = str(packet.get("packet_id") or "")
    snapshot["updated_utc"] = utc_now()
    document["eval_snapshot"] = snapshot
    write_json_atomic(path, document)


def evaluate_comparison_triggers(
    state: Path,
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return HELD comparison triggers whose frozen condition is met on the current packet."""
    supervisor = state / "supervisor"
    document = read_optional_json(comparison_trigger_path(supervisor))
    if not isinstance(document, dict):
        update_comparison_eval_snapshot(state, packet)
        return []
    rows = document.get("triggers")
    if not isinstance(rows, list) or not rows:
        update_comparison_eval_snapshot(state, packet)
        return []
    merged = _trigger_map(document)
    reconcile_comparison_triggers(merged)
    _write_trigger_document(state, merged, packet_id=str(document.get("packet_id") or ""))
    prior_price = _comparison_eval_snapshot(document).get("price")
    prior = float(prior_price) if isinstance(prior_price, (int, float)) and not isinstance(prior_price, bool) else None
    now = datetime.now(timezone.utc)
    fired: list[dict[str, Any]] = []
    for trigger in merged.values():
        if not isinstance(trigger, dict):
            continue
        if trigger.get("status") != "HELD":
            continue
        if _trigger_expired(trigger, now):
            continue
        if not _trigger_condition_met(trigger, packet, prior_price=prior):
            continue
        fired.append(trigger)
    update_comparison_eval_snapshot(state, packet)
    return fired


def comparison_wake_detail(trigger: dict[str, Any]) -> dict[str, Any]:
    trigger_id = str(trigger.get("trigger_id") or "")
    instrument = str(trigger.get("instrument") or "").upper()
    return {
        "wake_reason": f"COMPARISON_TRIGGER:{instrument}:{trigger_id}",
        "wake_trigger": {
            "type": "COMPARISON_TRIGGER",
            "trigger_id": trigger_id,
            "instrument": instrument,
            "condition": trigger.get("condition"),
            "path": trigger.get("path"),
        },
        "trigger_key": f"COMPARISON_TRIGGER:{trigger_id}",
    }
