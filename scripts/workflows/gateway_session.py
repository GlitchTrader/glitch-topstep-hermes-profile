"""Gateway delivery wire persistence and POST /intent orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from common import append_jsonl, read_optional_json, utc_now, write_json_atomic


def is_registered_delivery_conflict(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    body = result.get("body")
    return isinstance(body, dict) and body.get("code") == "intent_body_conflict"


def delivery_wire_path(state: Path, packet_id: str) -> Path:
    return state / "delivery-wire" / f"{packet_id}.json"


def load_delivery_wire(state: Path, packet_id: str) -> dict[str, Any] | None:
    payload = read_optional_json(delivery_wire_path(state, packet_id))
    if not isinstance(payload, dict):
        return None
    wire = payload.get("wire")
    return wire if isinstance(wire, dict) else None


def save_delivery_wire(state: Path, packet_id: str, wire: dict[str, Any]) -> None:
    delivery_wire_path(state, packet_id).parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        delivery_wire_path(state, packet_id),
        {
            "schema_version": "glitch.topstep.delivery_wire.v1",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": str(wire.get("intent_id") or ""),
            "wire": wire,
        },
    )


def clear_delivery_wire(state: Path, packet_id: str) -> None:
    try:
        delivery_wire_path(state, packet_id).unlink(missing_ok=True)
    except OSError:
        pass


def reconcile_registered_delivery(
    intent_id: str,
    packet_id: str,
    state: Path,
    post_intent: Callable[[dict[str, Any]], dict[str, Any]],
    fetch_receipt: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    wire = load_delivery_wire(state, packet_id)
    if wire is not None:
        retry = post_intent(wire)
        if not is_registered_delivery_conflict(retry):
            return retry
    if fetch_receipt is not None and intent_id:
        receipt = fetch_receipt(intent_id)
        if isinstance(receipt, dict):
            return {"http_status": 200, "body": receipt}
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "intent_delivery_unreconciled",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": intent_id,
        },
    )
    return {
        "http_status": 503,
        "body": {
            "code": "intent_delivery_unreconciled",
            "intent_id": intent_id,
        },
    }


def deliver_packet_intent(
    state: Path,
    packet_id: str,
    intent: dict[str, Any],
    directive: dict[str, Any] | None,
    post_intent: Callable[[dict[str, Any]], dict[str, Any]],
    prepare_intent_for_delivery: Callable[
        ...,
        dict[str, Any],
    ],
    fetch_receipt: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    wire = load_delivery_wire(state, packet_id)
    if wire is None:
        wire = prepare_intent_for_delivery(intent, directive, state=state)
        save_delivery_wire(state, packet_id, wire)
    result = post_intent(wire)
    if is_registered_delivery_conflict(result):
        result = reconcile_registered_delivery(
            str(intent.get("intent_id") or ""),
            packet_id,
            state,
            post_intent,
            fetch_receipt,
        )
    return result
