"""Learning journal persistence — outcomes and episode rows (audit C1)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from common import append_jsonl, read_jsonl, write_jsonl_atomic


def stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch-topstep:{kind}:{value}"))


def outcomes_path(root: Path) -> Path:
    configured = os.environ.get("GLITCH_TOPSTEP_OUTCOMES_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else root / "state" / "outcomes.jsonl"


def valid_outcomes(path: Path) -> list[dict[str, Any]]:
    required = {
        "schema_version", "outcome_id", "intent_id", "account", "instrument",
        "entry_utc", "exit_utc", "realized_pnl_usd", "fees_usd", "learning_eligible",
    }
    values = []
    for row in read_jsonl(path):
        if row.get("schema_version") != "glitch.topstep.trade_outcome.v1":
            continue
        if not required.issubset(row):
            continue
        if row.get("learning_eligible") is not True:
            continue
        values.append(row)
    return values


def canonical_outcomes(path: Path) -> list[dict[str, Any]]:
    required = {
        "schema_version", "outcome_id", "intent_id", "account", "instrument",
        "entry_utc", "exit_utc", "realized_pnl_usd", "fees_usd", "learning_eligible",
    }
    return [
        row for row in read_jsonl(path)
        if row.get("schema_version") == "glitch.topstep.trade_outcome.v1"
        and required.issubset(row)
    ]


def append_unique(path: Path, records: list[dict[str, Any]], id_field: str) -> None:
    existing = {str(row.get(id_field)) for row in read_jsonl(path) if row.get(id_field)}
    for record in records:
        identifier = str(record.get(id_field) or "")
        if identifier and identifier not in existing:
            append_jsonl(path, record)
            existing.add(identifier)


def upsert_unique(path: Path, records: list[dict[str, Any]], id_field: str) -> None:
    rows = read_jsonl(path)
    positions = {
        str(row.get(id_field)): index
        for index, row in enumerate(rows)
        if row.get(id_field)
    }
    for record in records:
        identifier = str(record.get(id_field) or "")
        if not identifier:
            continue
        position = positions.get(identifier)
        if position is None:
            positions[identifier] = len(rows)
            rows.append(record)
        else:
            rows[position] = record
    write_jsonl_atomic(path, rows)


def reconcile_corrected_episodes(
    path: Path,
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current = {str(row.get("outcome_id")): row for row in outcomes if row.get("outcome_id")}
    rows = read_jsonl(path)
    changed = False
    for episode in rows:
        outcome_id = str(episode.get("outcome_id") or "")
        outcome = current.get(outcome_id)
        if not outcome or outcome.get("learning_eligible") is True:
            continue
        if episode.get("status") != "retracted":
            episode["status"] = "retracted"
            episode["learning_eligible"] = False
            episode["retracted_revision"] = int(outcome.get("_feed_revision") or 1)
            episode["retraction_reason"] = "canonical_outcome_not_learning_eligible"
            changed = True
    if changed:
        write_jsonl_atomic(path, rows)
    return rows
