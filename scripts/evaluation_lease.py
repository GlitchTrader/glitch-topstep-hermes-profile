"""Production evaluation lease — cron defers while cognitive replay holds exclusivity."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import process_is_alive, process_matches_owner, process_start_utc, utc_now, write_json_atomic

EVALUATION_LEASE_FILENAME = "evaluation-lease.json"
LEASE_SCHEMA = "glitch.topstep.evaluation_lease.v1"
DEFAULT_TTL_SECONDS = 180


def evaluation_lease_path(state: Path) -> Path:
    return state / EVALUATION_LEASE_FILENAME


def _parse_utc(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def read_evaluation_lease(state: Path) -> dict[str, Any] | None:
    path = evaluation_lease_path(state)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _lease_holder_alive(lease: dict[str, Any]) -> bool:
    pid = int(lease.get("pid") or 0)
    if pid <= 0:
        return True
    try:
        if not process_is_alive(pid):
            return False
    except SystemError:
        return False
    return process_matches_owner(pid, lease.get("process_start_utc"))


def evaluation_lease_active(state: Path, *, now: datetime | None = None) -> bool:
    lease = read_evaluation_lease(state)
    if not isinstance(lease, dict):
        return False
    expires = _parse_utc(str(lease.get("expires_utc") or ""))
    current = now or datetime.now(timezone.utc)
    if expires is not None and current >= expires:
        return False
    if not _lease_holder_alive(lease):
        return False
    return True


def _remove_stale_lease(state: Path) -> None:
    lease = read_evaluation_lease(state)
    if not isinstance(lease, dict):
        evaluation_lease_path(state).unlink(missing_ok=True)
        return
    if evaluation_lease_active(state):
        return
    evaluation_lease_path(state).unlink(missing_ok=True)


def acquire_evaluation_lease(
    state: Path,
    *,
    run_id: str,
    invocation_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    state.mkdir(parents=True, exist_ok=True)
    path = evaluation_lease_path(state)
    _remove_stale_lease(state)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(30, int(ttl_seconds)))
    payload = {
        "schema_version": LEASE_SCHEMA,
        "run_id": run_id,
        "invocation_id": invocation_id,
        "pid": os.getpid(),
        "process_start_utc": (process_start_utc(os.getpid()) or now)
        .isoformat()
        .replace("+00:00", "Z"),
        "acquired_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_utc": expires.isoformat().replace("+00:00", "Z"),
        "renewed_utc": now.isoformat().replace("+00:00", "Z"),
    }
    for _ in range(3):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            current = read_evaluation_lease(state)
            if not isinstance(current, dict):
                time.sleep(0.02)
                _remove_stale_lease(state)
                continue
            if evaluation_lease_active(state):
                if str(current.get("run_id") or "") == run_id:
                    return renew_evaluation_lease(
                        state,
                        run_id=run_id,
                        invocation_id=invocation_id,
                        ttl_seconds=ttl_seconds,
                    )
                return False
            path.unlink(missing_ok=True)
            continue
        else:
            try:
                os.write(descriptor, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            finally:
                os.close(descriptor)
            return True
    return False


def renew_evaluation_lease(
    state: Path,
    *,
    run_id: str,
    invocation_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    current = read_evaluation_lease(state)
    if not isinstance(current, dict):
        return False
    if str(current.get("run_id") or "") != run_id:
        return False
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(30, int(ttl_seconds)))
    updated = {
        **current,
        "invocation_id": invocation_id,
        "pid": os.getpid(),
        "process_start_utc": (process_start_utc(os.getpid()) or now)
        .isoformat()
        .replace("+00:00", "Z"),
        "renewed_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_utc": expires.isoformat().replace("+00:00", "Z"),
    }
    write_json_atomic(evaluation_lease_path(state), updated)
    return True


def release_evaluation_lease(state: Path, *, run_id: str) -> None:
    current = read_evaluation_lease(state)
    if not isinstance(current, dict):
        return
    if str(current.get("run_id") or "") != run_id:
        return
    evaluation_lease_path(state).unlink(missing_ok=True)


def defer_production_worker_if_evaluation_lease(
    state: Path,
    *,
    worker_kind: str,
    run_id: str,
    status_path: Path,
    status_schema: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Return True when worker must defer (caller should exit 0)."""
    if not evaluation_lease_active(state):
        return False
    lease = read_evaluation_lease(state)
    body: dict[str, Any] = {
        "schema_version": status_schema,
        "run_id": run_id,
        "recorded_utc": utc_now(),
        "status": "deferred",
        "phase": "evaluation_lease_active",
        "retryable": True,
        "blocking_evaluation_run_id": (lease or {}).get("run_id"),
        "worker_kind": worker_kind,
    }
    if extra:
        body.update(extra)
    write_json_atomic(status_path, body)
    return True


class ProductionEvaluationLease:
    """Session-scoped production lease for cognitive replay runners."""

    def __init__(
        self,
        *,
        production_state: Path,
        run_id: str,
        invocation_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.production_state = production_state
        self.run_id = run_id
        self.invocation_id = invocation_id
        self.ttl_seconds = ttl_seconds
        self.acquired = False

    def acquire(self) -> bool:
        self.acquired = acquire_evaluation_lease(
            self.production_state,
            run_id=self.run_id,
            invocation_id=self.invocation_id,
            ttl_seconds=self.ttl_seconds,
        )
        return self.acquired

    def renew(self, *, invocation_id: str | None = None) -> bool:
        if not self.acquired:
            return False
        return renew_evaluation_lease(
            self.production_state,
            run_id=self.run_id,
            invocation_id=invocation_id or self.invocation_id,
            ttl_seconds=self.ttl_seconds,
        )

    def release(self) -> None:
        if self.acquired:
            release_evaluation_lease(self.production_state, run_id=self.run_id)
            self.acquired = False

    def __enter__(self) -> ProductionEvaluationLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
