"""Intent outbox queries and pruning — single writer path for outbox files."""

from __future__ import annotations

import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

from common import append_jsonl, read_optional_json, utc_now
from workflows.delivery_recovery import classify_delivery_result


def _minute_frames_dir(state_or_frames_root: Path) -> Path:
    nested = state_or_frames_root / "minute-frames"
    if nested.is_dir():
        return nested
    return state_or_frames_root


def frame_for_packet_id(state_or_frames_root: Path, packet_id: str) -> dict[str, Any] | None:
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
    reason: str | None = None
    if packet_for_outbox_id(state, packet_id) is None:
        intent_id = str(intent.get("intent_id") or "")
        if intent_id and token:
            import parity as parity_module

            try:
                status, body = parity_module.request_json(
                    f"/intent/receipt?intent_id={urllib.parse.quote(intent_id, safe='')}",
                    token=token,
                )
            except (OSError, TimeoutError, urllib.error.URLError):
                append_jsonl(
                    state / "events.jsonl",
                    {
                        "schema_version": "glitch.topstep.cycle_event.v2",
                        "event": "outbox_retained_delivery_unknown",
                        "recorded_utc": utc_now(),
                        "packet_id": packet_id,
                        "intent_id": intent_id,
                    },
                )
                return False
            if status == 200 and isinstance(body, dict):
                append_jsonl(
                    state / "events.jsonl",
                    {
                        "schema_version": "glitch.topstep.cycle_event.v2",
                        "event": "outbox_retained_gateway_receipt",
                        "recorded_utc": utc_now(),
                        "packet_id": packet_id,
                        "intent_id": intent_id,
                    },
                )
                return False
            if status not in (404, 410):
                append_jsonl(
                    state / "events.jsonl",
                    {
                        "schema_version": "glitch.topstep.cycle_event.v2",
                        "event": "outbox_retained_delivery_unknown",
                        "recorded_utc": utc_now(),
                        "packet_id": packet_id,
                        "intent_id": intent_id,
                        "http_status": status,
                    },
                )
                return False
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
