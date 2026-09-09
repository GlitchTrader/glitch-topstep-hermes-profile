"""Offline soak-lane plan for deferred data-quality cycles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import utc_now
from evaluation_owner import read_checkpoint, write_checkpoint

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "evaluation" / "deferred-data-quality-soak-lane.v1.json"
LANE_SCHEMA = "glitch.topstep.deferred_data_quality_soak_lane.v1"
VALID_CYCLE = "valid_cycle"
DEFERRED_DATA_QUALITY = "deferred_data_quality"


def load_lane_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    profiles = list(config.get("profiles") or [])
    if len(profiles) != 6:
        raise ValueError("six_profiles_required")
    if int((config.get("budget") or {}).get("max_parallel_slots") or 0) != 2:
        raise ValueError("max_parallel_slots_must_be_2")
    if any(p.get("execution_authority") is not False for p in profiles):
        raise ValueError("execution_authority_must_be_false")
    return config


def checkpoint_payload(config: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    return {
        "schema_version": LANE_SCHEMA,
        "run_id": run_id,
        "status": "planned",
        "t0_utc": None,
        "first_valid_cycle_id": None,
        "completed_cycles": 0,
        "valid_cycles": 0,
        "deferred_cycles": 0,
        "profiles": [str(p["profile_id"]) for p in config.get("profiles") or []],
        "max_parallel_slots": int((config.get("budget") or {}).get("max_parallel_slots") or 0),
        "execution_authority": False,
        "same_envelope_per_cycle": True,
        "writes_operacionais": 0,
        "resume_token": None,
    }


def advance_lane_checkpoint(
    checkpoint: dict[str, Any],
    *,
    cycle_id: str,
    cycle_status: str,
    packet_id: str | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    now = now_utc or utc_now()
    updated = dict(checkpoint)
    updated["completed_cycles"] = int(updated.get("completed_cycles") or 0) + 1
    updated["resume_token"] = cycle_id
    updated["last_cycle"] = {
        "cycle_id": cycle_id,
        "status": cycle_status,
        "packet_id": packet_id,
        "recorded_utc": now,
    }
    if cycle_status == VALID_CYCLE:
        updated["valid_cycles"] = int(updated.get("valid_cycles") or 0) + 1
        if not updated.get("t0_utc"):
            updated["t0_utc"] = now
            updated["first_valid_cycle_id"] = cycle_id
        updated["status"] = "running"
        return updated
    if cycle_status == DEFERRED_DATA_QUALITY:
        updated["deferred_cycles"] = int(updated.get("deferred_cycles") or 0) + 1
        updated["status"] = "running" if updated.get("t0_utc") else "awaiting_first_valid_cycle"
        return updated
    updated["status"] = "blocked"
    return updated


def persist_lane_checkpoint(state_root: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    write_checkpoint(state_root, checkpoint)
    payload = read_checkpoint(state_root)
    assert isinstance(payload, dict)
    return payload
