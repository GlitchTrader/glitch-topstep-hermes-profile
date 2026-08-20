"""Runtime lifecycle for multi-instrument comparison triggers (GTHP-TRIGGER-01)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import read_optional_json, utc_now, write_json_atomic
from scanner_contract import MARKER, TRIGGER_STATUSES


SCHEMA_VERSION = "glitch.topstep.comparison_triggers.v1"
PENDING_HELD_SCHEMA = "glitch.topstep.pending_held_rescan.v1"


def comparison_trigger_path(supervisor: Path) -> Path:
    return supervisor / "active-comparison-triggers.json"


def pending_held_rescan_path(supervisor: Path) -> Path:
    return supervisor / "pending-held-rescan.json"


def parse_comparison_ledger(intent: dict[str, Any]) -> dict[str, Any] | None:
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    text = audit.get("decisive_evidence")
    if not isinstance(text, str) or not text.startswith(MARKER):
        return None
    value = json.loads(text[len(MARKER) :])
    if not isinstance(value, dict):
        raise ValueError("instrument_comparison_invalid")
    return value


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


def persist_comparison_triggers(state: Path, intent: dict[str, Any], packet_id: str) -> None:
    ledger = parse_comparison_ledger(intent)
    if ledger is None:
        return
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    prior_doc = read_optional_json(comparison_trigger_path(supervisor))
    merged = merge_comparison_triggers(_trigger_map(prior_doc), ledger, packet_id=packet_id)
    write_json_atomic(
        comparison_trigger_path(supervisor),
        {
            "schema_version": SCHEMA_VERSION,
            "packet_id": packet_id,
            "updated_utc": utc_now(),
            "triggers": list(merged.values()),
        },
    )
    if str(intent.get("action") or "").upper() == "NOTHING" and any(
        row.get("status") == "HELD" for row in merged.values()
    ):
        write_json_atomic(
            pending_held_rescan_path(supervisor),
            {
                "schema_version": PENDING_HELD_SCHEMA,
                "recorded_utc": utc_now(),
                "source_packet_id": packet_id,
                "due_minute_utc": intent.get("created_utc") or utc_now(),
                "reason": "held_trigger_requires_rescan",
            },
        )


def pending_held_rescan_reason(state: Path) -> str | None:
    pending = read_optional_json(pending_held_rescan_path(state / "supervisor"))
    if pending:
        return "held_rescan"
    return None


def consume_pending_held_rescan(state: Path) -> None:
    pending_held_rescan_path(state / "supervisor").unlink(missing_ok=True)
