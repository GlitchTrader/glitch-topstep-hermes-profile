"""Single atomic Hermes CLI ownership lock (GTHP-RUNTIME-01 / Wave 1)."""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from common import (
    append_jsonl,
    process_is_alive,
    process_matches_owner,
    process_start_utc,
    read_json,
    utc_now,
)

OwnerKind = Literal["direct_cycle", "learning", "wake_monitor", "repair"]
OwnerState = Literal[
    "waiting",
    "active",
    "deferred",
    "preempted",
    "recovered",
    "failed",
    "completed",
]

PRIORITY = {
    "direct_cycle": 100,
    "repair": 90,
    "wake_monitor": 80,
    "learning": 10,
}

MODEL_OWNER_FILENAME = "model-owner.lock"
STATUS_FILENAME = "model-owner-status.json"
PREEMPT_GRACE_SECONDS = 15.0


def model_owner_lock_path(state: Path) -> Path:
    return state / MODEL_OWNER_FILENAME


def model_owner_status_path(state: Path) -> Path:
    return state / "supervisor" / STATUS_FILENAME


def _owner_alive(owner: dict[str, Any]) -> bool:
    pid = int(owner.get("pid") or 0)
    if pid <= 0:
        return False
    try:
        if not process_is_alive(pid):
            return False
    except SystemError:
        return False
    return process_matches_owner(pid, owner.get("process_start_utc"))


def active_model_owner(state: Path) -> dict[str, Any] | None:
    owner = read_model_owner(model_owner_lock_path(state))
    if isinstance(owner, dict) and _owner_alive(owner):
        return owner
    return None


def _read_generation(lock_path: Path) -> int:
    owner = read_model_owner(lock_path)
    if not isinstance(owner, dict):
        return 0
    try:
        return int(owner.get("generation") or 0)
    except (TypeError, ValueError):
        return 0


def _request_owner_stand_down(
    state: Path,
    lock_path: Path,
    owner: dict[str, Any],
    *,
    grace_seconds: float = PREEMPT_GRACE_SECONDS,
) -> bool:
    """Signal a live owner and wait for release before lock preemption (audit C1)."""
    pid = int(owner.get("pid") or 0)
    if pid <= 0:
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, SystemError):
        return not _owner_alive(owner)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _owner_alive(owner):
            return True
        current = read_model_owner(lock_path)
        if current is None:
            return True
        if str(current.get("invocation_id") or "") != str(owner.get("invocation_id") or ""):
            return True
        time.sleep(0.2)
    return not _owner_alive(owner)


def _owner_matches(current: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    if not isinstance(current, dict):
        return False
    for key in ("owner_kind", "invocation_id", "pid", "generation"):
        if str(current.get(key) or "") != str(expected.get(key) or ""):
            return False
    return True


def _remove_lock_if_owner(lock_path: Path, expected: dict[str, Any]) -> bool:
    """Compare-and-rename before unlink — avoids TOCTOU stealing a new owner (audit C2)."""
    current = read_model_owner(lock_path)
    if not _owner_matches(current, expected):
        return False
    stale_path = lock_path.with_suffix(".lock.stale")
    try:
        lock_path.replace(stale_path)
    except FileNotFoundError:
        return False
    stale_path.unlink(missing_ok=True)
    return True


def read_model_owner(lock_path: Path) -> dict[str, Any] | None:
    if not lock_path.is_file():
        return None
    try:
        owner = read_json(lock_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return owner if isinstance(owner, dict) else None


def publish_model_owner_status(state: Path, payload: dict[str, Any]) -> None:
    path = model_owner_status_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def acquire_model_owner(
    state: Path,
    *,
    owner_kind: OwnerKind,
    invocation_id: str,
    priority: int | None = None,
) -> bool:
    lock_path = model_owner_lock_path(state)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    effective_priority = priority if priority is not None else PRIORITY[owner_kind]
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    generation = _read_generation(lock_path) + 1
    payload = {
        "schema_version": "glitch.topstep.model_owner.v1",
        "owner_kind": owner_kind,
        "invocation_id": invocation_id,
        "pid": os.getpid(),
        "process_start_utc": (process_start_utc(os.getpid()) or datetime.now(timezone.utc))
        .isoformat()
        .replace("+00:00", "Z"),
        "acquired_utc": started,
        "priority": effective_priority,
        "generation": generation,
        "state": "active",
    }
    for _ in range(3):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            current = read_model_owner(lock_path)
            if current is None:
                # ponytail: concurrent partial write — retry without unlink (audit C2)
                time.sleep(0.02)
                continue
            if not _owner_alive(current):
                if not _remove_lock_if_owner(lock_path, current):
                    return False
                append_jsonl(
                    state / "events.jsonl",
                    {
                        "schema_version": "glitch.topstep.cycle_event.v2",
                        "event": "model_owner_recovered",
                        "recorded_utc": utc_now(),
                        "previous_owner_kind": current.get("owner_kind"),
                    },
                )
                continue
            current_priority = int(current.get("priority") or 0)
            if effective_priority > current_priority:
                append_jsonl(
                    state / "events.jsonl",
                    {
                        "schema_version": "glitch.topstep.cycle_event.v2",
                        "event": "model_owner_preempted",
                        "recorded_utc": utc_now(),
                        "preempted_owner_kind": current.get("owner_kind"),
                        "winner_owner_kind": owner_kind,
                        "preempted_pid": current.get("pid"),
                    },
                )
                if not _request_owner_stand_down(state, lock_path, current):
                    publish_model_owner_status(
                        state,
                        {
                            "schema_version": "glitch.topstep.model_owner_status.v1",
                            "recorded_utc": utc_now(),
                            "state": "deferred",
                            "owner_kind": owner_kind,
                            "blocking_owner_kind": current.get("owner_kind"),
                            "detail": "preempt_timeout",
                        },
                    )
                    return False
                if not _remove_lock_if_owner(lock_path, current):
                    return False
                continue
            publish_model_owner_status(
                state,
                {
                    "schema_version": "glitch.topstep.model_owner_status.v1",
                    "recorded_utc": utc_now(),
                    "state": "deferred",
                    "owner_kind": owner_kind,
                    "blocking_owner_kind": current.get("owner_kind"),
                },
            )
            return False
        else:
            try:
                os.write(descriptor, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            finally:
                os.close(descriptor)
            publish_model_owner_status(state, payload)
            return True
    publish_model_owner_status(
        state,
        {
            "schema_version": "glitch.topstep.model_owner_status.v1",
            "recorded_utc": utc_now(),
            "state": "waiting",
            "owner_kind": owner_kind,
        },
    )
    return False


def release_model_owner(state: Path, *, owner_kind: OwnerKind, invocation_id: str) -> None:
    lock_path = model_owner_lock_path(state)
    current = read_model_owner(lock_path)
    if not isinstance(current, dict):
        return
    if (
        str(current.get("owner_kind") or "") != owner_kind
        or str(current.get("invocation_id") or "") != invocation_id
    ):
        return
    if not _remove_lock_if_owner(lock_path, current):
        return
    publish_model_owner_status(
        state,
        {
            "schema_version": "glitch.topstep.model_owner_status.v1",
            "recorded_utc": utc_now(),
            "state": "completed",
            "owner_kind": owner_kind,
            "invocation_id": invocation_id,
        },
    )
