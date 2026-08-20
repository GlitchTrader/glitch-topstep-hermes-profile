"""Session calibration metrics for weekly learning evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _range_position_20(packet: dict[str, Any]) -> float | None:
    observation_state = packet.get("market_observation")
    if not isinstance(observation_state, dict):
        return None
    observation = observation_state.get("observation")
    if not isinstance(observation, dict):
        return None
    for timeframe in observation.get("timeframes") or []:
        if not isinstance(timeframe, dict):
            continue
        if timeframe.get("timeframe_minutes") not in {5, 60}:
            continue
        features = timeframe.get("features")
        if not isinstance(features, dict):
            continue
        value = features.get("range_position_20")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _receipt_is_schema_invalid(receipt: dict[str, Any]) -> bool:
    result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
    http_status = result.get("http_status")
    if http_status == 422:
        return True
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    for key in ("error", "code", "message"):
        text = str(body.get(key) or "")
        if "intent_schema_invalid" in text:
            return True
    return False


def _load_receipts(state_root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(state_root / "receipts.jsonl")
    receipts_dir = state_root / "receipts"
    if receipts_dir.is_dir():
        for path in sorted(receipts_dir.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _frame_packet_for_decision(
    state_root: Path,
    packet_id: str,
) -> dict[str, Any] | None:
    frame_path = state_root / "minute-frames" / f"{packet_id}.json"
    if not frame_path.is_file():
        return None
    try:
        frame = json.loads(frame_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    packet = frame.get("packet") if isinstance(frame, dict) else None
    return packet if isinstance(packet, dict) else None


def compute_session_metrics(state_root: Path) -> dict[str, float | None]:
    """Return schema_validity_rate, late_entry_pct, missed_participation_pct."""
    receipts = _load_receipts(state_root)
    receipt_total = len(receipts)
    invalid_count = sum(1 for row in receipts if _receipt_is_schema_invalid(row))
    if receipt_total:
        schema_validity_rate = (receipt_total - invalid_count) / receipt_total
    else:
        schema_validity_rate = None

    episodes_path = state_root / "supervisor" / "decision-episodes.jsonl"
    episodes = _read_jsonl(episodes_path)
    classified = [
        row
        for row in episodes
        if isinstance(row.get("classification"), str) and row.get("classification")
    ]
    if not classified:
        classified = [
            row
            for row in episodes
            if isinstance(row.get("classification_hint"), str)
            and row.get("classification_hint")
        ]
    missed = sum(
        1
        for row in classified
        if str(row.get("classification") or row.get("classification_hint"))
        == "missed_directional_participation"
    )
    missed_participation_pct = (
        missed / len(classified) if classified else None
    )

    entry_total = 0
    late_entries = 0
    for row in _read_jsonl(state_root / "decisions.jsonl"):
        intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
        action = str(intent.get("action") or "")
        if action not in {"ENTER_LONG", "ENTER_SHORT"}:
            continue
        packet_id = str(row.get("packet_id") or intent.get("packet_id") or "")
        packet = _frame_packet_for_decision(state_root, packet_id)
        if packet is None:
            continue
        range_pos = _range_position_20(packet)
        if range_pos is None:
            continue
        entry_total += 1
        if range_pos > 0.85 or range_pos < 0.15:
            late_entries += 1
    late_entry_pct = late_entries / entry_total if entry_total else None

    return {
        "schema_validity_rate": schema_validity_rate,
        "late_entry_pct": late_entry_pct,
        "missed_participation_pct": missed_participation_pct,
    }
