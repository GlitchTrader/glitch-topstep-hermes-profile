"""Intent outbox queries and pruning — single writer path for outbox files."""

from __future__ import annotations

import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Literal

from common import append_jsonl, parse_utc, read_optional_json, utc_now
from workflows.delivery_recovery import classify_delivery_result

ReceiptGateResult = Literal["discard", "retain_receipt", "retain_unknown"]

SUPERSESSION_DELIVERY_ERRORS = frozenset({
    "packet_superseded_before_delivery",
    "entry_intent_expired",
    "entry_scope_superseded",
    "entry_range_superseded",
})


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


def _intent_delivery_status(intent_id: str, *, token: str) -> tuple[int, dict[str, Any] | None]:
    import parity as parity_module

    return parity_module.request_json(
        f"/intent/status?intent_id={urllib.parse.quote(intent_id, safe='')}",
        token=token,
    )


def gateway_receipt_gate(
    state: Path,
    packet_id: str,
    intent: dict[str, Any],
    *,
    token: str,
) -> ReceiptGateResult:
    intent_id = str(intent.get("intent_id") or "")
    if not intent_id or not token:
        return "discard"
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
        return "retain_unknown"
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
        return "retain_receipt"
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
        return "retain_unknown"
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "outbox_retained_receipt_only_not_found",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": intent_id,
            "http_status": status,
        },
    )
    return "retain_unknown"


def supersession_discard_reason(
    intent: dict[str, Any],
    current_packet: dict[str, Any],
    outbox_packet_id: str,
) -> str | None:
    expires_utc = intent.get("expires_utc")
    if expires_utc:
        try:
            if parse_utc(expires_utc) < parse_utc(utc_now()):
                return "packet_lease_expired"
        except (TypeError, ValueError):
            pass
    current_id = str(current_packet.get("packet_id") or "")
    if current_id and current_id != outbox_packet_id:
        return "packet_superseded"
    return None


def _emit_discarded_stale_packet(
    state: Path,
    *,
    reason: str,
    packet_id: str,
    intent: dict[str, Any],
) -> None:
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "intent_discarded_stale_packet",
            "reason": reason,
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": str(intent.get("intent_id") or ""),
            "action": str(intent.get("action") or ""),
        },
    )


def discard_outbox_after_receipt_gate(
    state: Path,
    outbox_path: Path,
    packet_id: str,
    intent: dict[str, Any],
    reason: str,
    *,
    token: str,
) -> bool:
    intent_id = str(intent.get("intent_id") or "")
    if reason in {"packet_superseded", "packet_lease_expired"}:
        status_code, body = _intent_delivery_status(intent_id, token=token)
        if status_code != 200 or not isinstance(body, dict) or body.get("status") != "not_seen":
            append_jsonl(
                state / "events.jsonl",
                {
                    "schema_version": "glitch.topstep.cycle_event.v2",
                    "event": "outbox_retained_delivery_unknown",
                    "recorded_utc": utc_now(),
                    "packet_id": packet_id,
                    "intent_id": intent_id,
                    "reason": reason,
                    "delivery_status": body.get("status") if isinstance(body, dict) else None,
                },
            )
            return False
    gate = gateway_receipt_gate(state, packet_id, intent, token=token)
    if gate != "discard":
        return False
    try:
        outbox_path.unlink(missing_ok=True)
    except OSError:
        return False
    _emit_discarded_stale_packet(
        state,
        reason=reason,
        packet_id=packet_id,
        intent=intent,
    )
    return True


def discard_superseded_pending_outbox(
    state: Path,
    outbox_path: Path,
    outbox_packet_id: str,
    intent: dict[str, Any],
    current_packet: dict[str, Any],
    *,
    token: str,
) -> bool:
    reason = supersession_discard_reason(intent, current_packet, outbox_packet_id)
    if reason is None:
        return False
    return discard_outbox_after_receipt_gate(
        state,
        outbox_path,
        outbox_packet_id,
        intent,
        reason,
        token=token,
    )


def discard_superseded_delivery_error(
    state: Path,
    outbox_path: Path,
    packet_id: str,
    intent: dict[str, Any],
    error: BaseException,
    *,
    token: str,
) -> bool:
    message = str(error)
    if message not in SUPERSESSION_DELIVERY_ERRORS:
        return False
    reason = message if message != "packet_superseded_before_delivery" else "packet_superseded"
    return discard_outbox_after_receipt_gate(
        state,
        outbox_path,
        packet_id,
        intent,
        reason,
        token=token,
    )


def discard_stale_outbox_intent(
    state: Path,
    outbox_path: Path,
    packet_id: str,
    intent: dict[str, Any],
    *,
    token: str,
) -> bool:
    if packet_for_outbox_id(state, packet_id) is not None:
        return False
    return discard_outbox_after_receipt_gate(
        state,
        outbox_path,
        packet_id,
        intent,
        "stored_packet_not_found",
        token=token,
    )
