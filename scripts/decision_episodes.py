"""Collect decision episodes for Topstep learning supervision."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from common import append_jsonl, read_jsonl, read_optional_json, utc_now

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
}


def stable_episode_id(intent_id: str) -> str:
    return str(uuid.uuid5(uuid.NamespaceURL, f"glitch-topstep:decision:{intent_id}"))


def _receipt_body(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt:
        return {}
    result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    return body if isinstance(body, dict) else {}


def _classify_decision(intent: dict[str, Any], receipt: dict[str, Any] | None, attempt_error: str | None) -> str:
    action = str(intent.get("action") or "").upper()
    if attempt_error:
        for code in COGNITIVE_FIREWALL_REJECTIONS:
            if code in attempt_error:
                return "policy_rejection"
        return "system_defect"
    body = _receipt_body(receipt)
    if body.get("shadow_only") is True or str(body.get("trading_mode") or "").lower() == "shadow":
        return "shadow_only"
    if action in {"NOTHING", "HOLD"}:
        return "abstention"
    if action in {"ENTER_LONG", "ENTER_SHORT", "EXIT", "MOVE_STOP"}:
        return "action_submitted"
    return "other"


def collect_decision_episodes(state: Path, *, future_frame_count: int = 3) -> list[dict[str, Any]]:
    output_path = state / "supervisor" / "decision-episodes.jsonl"
    existing = {str(row.get("intent_id")) for row in read_jsonl(output_path) if row.get("intent_id")}
    frames_root = state / "minute-frames"
    frame_paths = sorted(frames_root.glob("*.json"))
    frame_index = {path.stem: path for path in frame_paths}
    records: list[dict[str, Any]] = []

    for row in read_jsonl(state / "decisions.jsonl"):
        intent = row.get("intent")
        if not isinstance(intent, dict) or not intent.get("intent_id"):
            continue
        intent_id = str(intent["intent_id"])
        if intent_id in existing:
            continue
        packet_id = str(row.get("packet_id") or "")
        receipt = read_optional_json(state / "receipts" / f"{packet_id}.json") if packet_id else None
        attempt = read_optional_json(state / "attempts" / f"{packet_id}.json") if packet_id else None
        attempt_error = str(attempt.get("error") or "") if attempt else ""
        minute_id = packet_id[:13] + "Z" if packet_id.endswith("Z") and len(packet_id) > 13 else packet_id
        future_keys = [key for key in sorted(frame_index) if key > minute_id][:future_frame_count]
        if minute_id and len(future_keys) < min(future_frame_count, 1):
            continue
        packet_frame = read_optional_json(frame_index.get(minute_id)) if minute_id in frame_index else None
        market_last = None
        if packet_frame and isinstance(packet_frame.get("packet"), dict):
            market = packet_frame["packet"].get("market")
            if isinstance(market, dict):
                market_last = market.get("last")
        records.append({
            "schema_version": "glitch.topstep.decision_episode.v1",
            "episode_id": stable_episode_id(intent_id),
            "recorded_utc": utc_now(),
            "intent_id": intent_id,
            "packet_id": packet_id,
            "action": intent.get("action"),
            "confidence": intent.get("confidence"),
            "classification": _classify_decision(intent, receipt, attempt_error or None),
            "shadow_only": _classify_decision(intent, receipt, attempt_error or None) == "shadow_only",
            "attempt_error": attempt_error[:240] if attempt_error else None,
            "market_last": market_last,
            "future_frame_count": len(future_keys),
            "reason_excerpt": str(intent.get("reason") or "")[:240],
        })
    if records:
        for record in records:
            append_jsonl(output_path, record)
    return read_jsonl(output_path)
