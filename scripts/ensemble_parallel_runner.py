"""Parallel profile execution within evaluation lane (fixture/offline-first)."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROFILE_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ProfileSlotResult:
    profile_id: str
    invocation_id: str
    work_dir: str
    started_utc: str
    finished_utc: str
    latency_ms: int
    cancelled: bool
    error: str | None
    raw_profile_output: dict[str, Any] | None
    normalized: dict[str, Any] | None
    estimated_cost_usd: float = 0.0


@dataclass
class ParallelRunState:
    max_parallel_slots: int
    session_cost_usd: float = 0.0
    cancel_remaining: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_cost(self, amount: float) -> None:
        with self.lock:
            self.session_cost_usd += amount

    def budget_exceeded(self, max_cost: float) -> bool:
        with self.lock:
            return self.session_cost_usd >= max_cost


def _isolated_work_dir(run_id: str, profile_id: str, frame_id: str) -> Path:
    base = PROFILE_ROOT / "evaluation" / "runs" / "parallel_slots" / run_id
    safe_profile = profile_id.replace("/", "_")
    path = base / safe_profile / frame_id / str(uuid.uuid4())
    path.mkdir(parents=True, exist_ok=True)
    marker = path / "HERMES_HOME_ISOLATED"
    marker.write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "frame_id": frame_id,
                "run_id": run_id,
                "evaluation_only": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def execute_profile_slot(
    *,
    profile: dict[str, Any],
    frame_id: str,
    run_id: str,
    work_dir: Path,
    loader: Callable[[str, str], dict[str, Any] | None],
    builder: Callable[..., dict[str, Any]],
    envelope: dict[str, Any],
    gate: dict[str, Any],
    run_state: ParallelRunState,
    max_cost_usd: float,
    timeout_ms: int,
) -> ProfileSlotResult:
    profile_id = str(profile["profile_id"])
    invocation_id = str(uuid.uuid4())
    started = utc_now()
    cancelled = run_state.cancel_remaining.is_set()
    if cancelled or run_state.budget_exceeded(max_cost_usd):
        return ProfileSlotResult(
            profile_id=profile_id,
            invocation_id=invocation_id,
            work_dir=str(work_dir),
            started_utc=started,
            finished_utc=utc_now(),
            latency_ms=0,
            cancelled=True,
            error="cancelled_or_budget",
            raw_profile_output=None,
            normalized=None,
        )

    raw: dict[str, Any] | None = None
    error: str | None = None
    latency_ms = 0
    try:
        raw = loader(profile_id, frame_id)
        if raw is None:
            error = "fixture_missing"
        latency_ms = int(raw.get("latency_ms") or 1) if raw else 0
        if latency_ms > timeout_ms:
            error = "timeout"
            raw = {"state": "timeout", "latency_ms": latency_ms}
    except Exception as exc:  # ponytail: classify provider failures without crashing pool
        error = f"provider_error:{exc}"
        raw = {"state": "error", "error_code": str(exc)}

    normalized = builder(
        fixture=raw if error != "fixture_missing" else None,
        run_id=run_id,
        profile=profile,
        envelope=envelope,
        gate=gate,
        started_utc=started,
        finished_utc=utc_now(),
        latency_ms=latency_ms if error != "timeout" else timeout_ms + 1,
    )
    cost = float((raw or {}).get("estimated_cost_usd") or 0.01)
    run_state.add_cost(cost)
    return ProfileSlotResult(
        profile_id=profile_id,
        invocation_id=invocation_id,
        work_dir=str(work_dir),
        started_utc=started,
        finished_utc=utc_now(),
        latency_ms=latency_ms,
        cancelled=cancelled,
        error=error,
        raw_profile_output=raw,
        normalized=normalized,
        estimated_cost_usd=cost,
    )


def run_profiles_parallel(
    *,
    profiles: list[dict[str, Any]],
    frame_id: str,
    run_id: str,
    envelope: dict[str, Any],
    gates_by_profile: dict[str, dict[str, Any]],
    loader: Callable[[str, str], dict[str, Any] | None],
    builder: Callable[..., dict[str, Any]],
    max_parallel_slots: int = 2,
    max_cost_usd: float = 2.5,
    per_profile_timeout_ms: int = 35000,
    total_timeout_ms: int = 120000,
) -> list[ProfileSlotResult]:
    """Run profile invocations with bounded parallelism and isolated work dirs."""
    run_state = ParallelRunState(max_parallel_slots=max(1, max_parallel_slots))
    results: list[ProfileSlotResult] = []
    work_dirs: list[Path] = []

    def _task(profile: dict[str, Any]) -> ProfileSlotResult:
        pid = str(profile["profile_id"])
        work_dir = _isolated_work_dir(run_id, pid, frame_id)
        work_dirs.append(work_dir)
        return execute_profile_slot(
            profile=profile,
            frame_id=frame_id,
            run_id=run_id,
            work_dir=work_dir,
            loader=loader,
            builder=builder,
            envelope=envelope,
            gate=gates_by_profile.get(pid, {}),
            run_state=run_state,
            max_cost_usd=max_cost_usd,
            timeout_ms=per_profile_timeout_ms,
        )

    with ThreadPoolExecutor(max_workers=max_parallel_slots) as pool:
        futures = {pool.submit(_task, profile): profile for profile in profiles}
        total_wait_ms = 0
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            total_wait_ms += result.latency_ms
            if total_wait_ms > total_timeout_ms:
                run_state.cancel_remaining.set()

    return sorted(results, key=lambda row: row.profile_id)


def cleanup_work_dirs(run_id: str) -> None:
    base = PROFILE_ROOT / "evaluation" / "runs" / "parallel_slots" / run_id
    if base.is_dir():
        shutil.rmtree(base, ignore_errors=True)
