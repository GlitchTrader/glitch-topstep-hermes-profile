"""Wake trigger evaluation and persistence (GTHP-AUDIT-04)."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from common import (
    append_jsonl,
    parse_utc,
    read_json,
    read_optional_json,
    utc_now,
    write_json_atomic,
)

WAKE_TRIGGER_SCHEMA = "glitch.topstep.wake_triggers.v1"
WAKE_TRIGGER_TYPES = frozenset({"PRICE_CROSS", "SESSION_PHASE"})
SESSION_PHASE_VALUES = frozenset({"regular", "maintenance", "asia"})
# ponytail: TAPE_BURST and DOM_IMBALANCE deferred until gateway tape/DOM wake fields stabilize.


def order_flow_window(packet: dict[str, Any], window_seconds: int) -> dict[str, Any] | None:
    order_flow = packet.get("order_flow")
    if not isinstance(order_flow, dict):
        return None
    observation = order_flow.get("observation")
    if not isinstance(observation, dict):
        return None
    windows = observation.get("windows")
    if not isinstance(windows, list):
        return None
    for window in windows:
        if isinstance(window, dict) and window.get("window_seconds") == window_seconds:
            return window
    return None


def wake_trigger_path(supervisor: Path) -> Path:
    return supervisor / "active-wake-triggers.json"


def wake_trigger_cooldown_seconds() -> int:
    raw = os.environ.get("GLITCH_TOPSTEP_WAKE_TRIGGER_COOLDOWN_SECONDS", "120")
    try:
        value = int(raw)
    except ValueError:
        value = 120
    return max(0, value)


def wake_trigger_key(trigger: dict[str, Any]) -> str:
    trigger_type = str(trigger.get("type") or "")
    if trigger_type == "PRICE_CROSS":
        return f"PRICE_CROSS:{trigger.get('direction')}:{trigger.get('price')}"
    if trigger_type == "SESSION_PHASE":
        return f"SESSION_PHASE:{trigger.get('phase')}"
    return json.dumps(trigger, sort_keys=True, separators=(",", ":"))


def wake_reason_label(trigger: dict[str, Any]) -> str:
    trigger_type = str(trigger.get("type") or "")
    if trigger_type == "PRICE_CROSS":
        return f"PRICE_CROSS:{trigger.get('direction')}:{trigger.get('price')}"
    if trigger_type == "SESSION_PHASE":
        return f"SESSION_PHASE:{trigger.get('phase')}"
    return wake_trigger_key(trigger)


def validate_wake_triggers(triggers: Any) -> None:
    if not isinstance(triggers, list):
        raise ValueError("wake_triggers_invalid")
    for trigger_index, trigger in enumerate(triggers):
        if not isinstance(trigger, dict):
            raise ValueError(f"wake_trigger_invalid:{trigger_index}")
        trigger_type = trigger.get("type")
        if trigger_type not in WAKE_TRIGGER_TYPES:
            raise ValueError(f"wake_trigger_type_invalid:{trigger_index}")
        if trigger_type == "PRICE_CROSS":
            allowed = {"type", "direction", "price"}
            if set(trigger) != allowed:
                raise ValueError(f"wake_trigger_fields_invalid:{trigger_index}")
            if trigger.get("direction") not in {"ABOVE", "BELOW"}:
                raise ValueError(f"wake_trigger_direction_invalid:{trigger_index}")
            price = trigger.get("price")
            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(float(price))
            ):
                raise ValueError(f"wake_trigger_price_invalid:{trigger_index}")
        elif trigger_type == "SESSION_PHASE":
            allowed = {"type", "phase"}
            if set(trigger) != allowed:
                raise ValueError(f"wake_trigger_fields_invalid:{trigger_index}")
            if trigger.get("phase") not in SESSION_PHASE_VALUES:
                raise ValueError(f"wake_trigger_phase_invalid:{trigger_index}")


def explicit_price_crosses(condition: str) -> set[tuple[str, float]]:
    pattern = re.compile(
        r"\b(above|over|below|under)\s+([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    crosses: set[tuple[str, float]] = set()
    for match in pattern.finditer(condition):
        direction = "ABOVE" if match.group(1).lower() in {"above", "over"} else "BELOW"
        crosses.add((direction, float(match.group(2))))
    return crosses


def require_explicit_wake_triggers(
    audit: dict[str, Any],
    triggers: list[dict[str, Any]],
) -> None:
    """Advisory helper only; change_condition price language is not a worker gate."""
    _ = audit
    _ = triggers


def packet_current_price(packet: dict[str, Any]) -> float | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    value = market.get("last")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def packet_one_minute_range(packet: dict[str, Any]) -> tuple[float, float] | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    try:
        close = float(market["last"])
    except (KeyError, TypeError, ValueError):
        return None
    window = order_flow_window(packet, 60)
    if window is not None:
        try:
            return float(window["low_price"]), float(window["high_price"])
        except (KeyError, TypeError, ValueError):
            pass
    for high_key, low_key in (("session_high", "session_low"), ("high", "low")):
        try:
            return float(market[low_key]), float(market[high_key])
        except (KeyError, TypeError, ValueError):
            continue
    return close, close


def prior_frame_price(state: Path, packet: dict[str, Any]) -> float | None:
    frames_dir = state / "minute-frames"
    if not frames_dir.is_dir():
        return None
    current_id = parse_utc(packet["created_utc"]).strftime("%Y%m%dT%H%MZ")
    for path in sorted(frames_dir.glob("*.json"), reverse=True):
        if path.stem >= current_id:
            continue
        frame = read_optional_json(path)
        if not frame:
            continue
        prior_packet = frame.get("packet")
        if isinstance(prior_packet, dict):
            price = packet_current_price(prior_packet)
            if price is not None:
                return price
    return None


def read_wake_trigger_document(state: Path) -> dict[str, Any] | None:
    path = wake_trigger_path(state / "supervisor")
    if not path.is_file():
        return None
    try:
        value = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def packet_session_phase(packet: dict[str, Any]) -> str | None:
    session = packet.get("session") if isinstance(packet.get("session"), dict) else {}
    phase = session.get("phase")
    if phase in SESSION_PHASE_VALUES:
        return str(phase)
    return None


def prior_eval_snapshot(state: Path, packet: dict[str, Any]) -> tuple[float | None, str | None]:
    document = read_wake_trigger_document(state)
    snapshot = document.get("eval_snapshot") if isinstance(document, dict) else None
    prior_price: float | None = None
    prior_phase: str | None = None
    if isinstance(snapshot, dict):
        raw_price = snapshot.get("price")
        if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
            if math.isfinite(float(raw_price)):
                prior_price = float(raw_price)
        raw_phase = snapshot.get("phase")
        if raw_phase in SESSION_PHASE_VALUES:
            prior_phase = str(raw_phase)
    if prior_price is None:
        prior_price = prior_frame_price(state, packet)
    return prior_price, prior_phase


def update_wake_eval_snapshot(state: Path, packet: dict[str, Any]) -> None:
    document = read_wake_trigger_document(state)
    if not isinstance(document, dict):
        return
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    current_price = packet_current_price(packet)
    current_phase = packet_session_phase(packet)
    snapshot: dict[str, Any] = {"updated_utc": utc_now()}
    if current_price is not None:
        snapshot["price"] = current_price
    if current_phase is not None:
        snapshot["phase"] = current_phase
    document["eval_snapshot"] = snapshot
    write_json_atomic(wake_trigger_path(supervisor), document)


def trigger_in_cooldown(document: dict[str, Any], trigger: dict[str, Any]) -> bool:
    cooldown = wake_trigger_cooldown_seconds()
    if cooldown <= 0:
        return False
    history = document.get("fire_history")
    if not isinstance(history, dict):
        return False
    entry = history.get(wake_trigger_key(trigger))
    if not isinstance(entry, dict):
        return False
    fired_utc = entry.get("last_fired_utc")
    if not isinstance(fired_utc, str):
        return False
    try:
        fired_at = parse_utc(fired_utc)
    except (ValueError, TypeError):
        return False
    return (parse_utc(utc_now()) - fired_at).total_seconds() < cooldown


def record_wake_trigger_fire(
    state: Path,
    trigger: dict[str, Any],
    packet: dict[str, Any],
    *,
    source: str,
) -> None:
    document = read_wake_trigger_document(state) or {
        "schema_version": WAKE_TRIGGER_SCHEMA,
        "triggers": [],
    }
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    history = document.get("fire_history")
    if not isinstance(history, dict):
        history = {}
    packet_id = str(packet.get("packet_id") or "")
    history[wake_trigger_key(trigger)] = {
        "last_fired_utc": utc_now(),
        "last_packet_id": packet_id,
        "wake_reason": wake_reason_label(trigger),
        "source": source,
    }
    document["fire_history"] = history
    write_json_atomic(wake_trigger_path(supervisor), document)
    append_jsonl(
        state / "events.jsonl",
        {
            "schema_version": "glitch.topstep.cycle_event.v2",
            "event": "wake_trigger_fired",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "wake_reason": wake_reason_label(trigger),
            "wake_trigger": trigger,
            "source": source,
            "cooldown_seconds": wake_trigger_cooldown_seconds(),
        },
    )


def _price_cross_fired(
    trigger: dict[str, Any],
    previous: float | None,
    current: float | None,
    current_range: tuple[float, float] | None,
) -> bool:
    if previous is None or current is None:
        return False
    try:
        level = float(trigger["price"])
    except (KeyError, TypeError, ValueError):
        return False
    current_low, current_high = current_range or (current, current)
    direction = trigger.get("direction")
    if direction == "ABOVE" and previous <= level < max(current, current_high):
        return True
    if direction == "BELOW" and previous >= level > min(current, current_low):
        return True
    return False


def _session_phase_fired(
    trigger: dict[str, Any],
    previous_phase: str | None,
    current_phase: str | None,
) -> bool:
    if previous_phase is None or current_phase is None:
        return False
    target = trigger.get("phase")
    return previous_phase != target and current_phase == target


def evaluate_wake_triggers(
    state: Path,
    packet: dict[str, Any],
    *,
    record_fire: bool = False,
    source: str = "cycle",
) -> dict[str, Any] | None:
    document = read_wake_trigger_document(state)
    if not isinstance(document, dict):
        update_wake_eval_snapshot(state, packet)
        return None
    triggers = document.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        update_wake_eval_snapshot(state, packet)
        return None
    previous_price, previous_phase = prior_eval_snapshot(state, packet)
    current_price = packet_current_price(packet)
    current_range = packet_one_minute_range(packet)
    current_phase = packet_session_phase(packet)
    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue
        trigger_type = trigger.get("type")
        fired = False
        if trigger_type == "PRICE_CROSS":
            fired = _price_cross_fired(trigger, previous_price, current_price, current_range)
        elif trigger_type == "SESSION_PHASE":
            fired = _session_phase_fired(trigger, previous_phase, current_phase)
        if not fired:
            continue
        if trigger_in_cooldown(document, trigger):
            continue
        detail = {
            "wake_reason": wake_reason_label(trigger),
            "wake_trigger": trigger,
            "trigger_key": wake_trigger_key(trigger),
        }
        if record_fire:
            record_wake_trigger_fire(state, trigger, packet, source=source)
        update_wake_eval_snapshot(state, packet)
        return detail
    update_wake_eval_snapshot(state, packet)
    return None


def wake_trigger_fired(state: Path, packet: dict[str, Any]) -> bool:
    return evaluate_wake_triggers(state, packet) is not None


def persist_wake_triggers(state: Path, intent: dict[str, Any], packet_id: str) -> None:
    triggers = intent.get("wake_triggers")
    if not isinstance(triggers, list):
        triggers = []
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    existing = read_wake_trigger_document(state) or {}
    fire_history = existing.get("fire_history")
    eval_snapshot = existing.get("eval_snapshot")
    document: dict[str, Any] = {
        "schema_version": WAKE_TRIGGER_SCHEMA,
        "packet_id": packet_id,
        "triggers": triggers,
        "updated_utc": utc_now(),
        "cooldown_seconds": wake_trigger_cooldown_seconds(),
    }
    if isinstance(fire_history, dict):
        document["fire_history"] = fire_history
    if isinstance(eval_snapshot, dict):
        document["eval_snapshot"] = eval_snapshot
    write_json_atomic(wake_trigger_path(supervisor), document)


def pending_wake_path(supervisor: Path) -> Path:
    return supervisor / "pending-wake-invocation.json"


def write_pending_wake_invocation(state: Path, wake_detail: dict[str, Any], packet: dict[str, Any]) -> None:
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        pending_wake_path(supervisor),
        {
            "schema_version": "glitch.topstep.pending_wake.v1",
            "recorded_utc": utc_now(),
            "packet_id": str(packet.get("packet_id") or ""),
            "wake_reason": wake_detail.get("wake_reason"),
            "wake_trigger": wake_detail.get("wake_trigger"),
            "trigger_key": wake_detail.get("trigger_key"),
        },
    )


def read_pending_wake_invocation(state: Path) -> dict[str, Any] | None:
    path = pending_wake_path(state / "supervisor")
    value = read_optional_json(path)
    return value if isinstance(value, dict) else None


def clear_pending_wake_invocation(state: Path) -> None:
    path = pending_wake_path(state / "supervisor")
    path.unlink(missing_ok=True)


def cycle_wake_fields(
    reason: str | None,
    wake_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {"invocation_reason": reason}
    if wake_detail:
        fields["wake_reason"] = wake_detail.get("wake_reason")
        fields["wake_trigger"] = wake_detail.get("wake_trigger")
    return fields
