"""Shared helpers for sequential and parallel ensemble evaluation runners."""

from __future__ import annotations

import ast
import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation_output_adapter import adapt_evaluation_output
from ensemble_envelope import envelope_hash

# Evaluation runners must not import production workflows or delivery paths.
FORBIDDEN_IMPORT_PREFIXES = (
    "workflows.",
    "run_topstep_cycle",
    "run-topstep-cycle",
    "intent_outbox",
    "model_owner_lock",
    "entry_delivery",
)

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"workflows", "intent_outbox", "model_owner_lock", "entry_delivery"}
)


def assert_runner_isolation(runner_source: Path) -> None:
    """Reject forbidden production imports in a runner source file."""
    source = Path(runner_source).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                if module == forbidden.rstrip(".") or module.startswith(forbidden):
                    raise RuntimeError(f"runner_forbidden_import:{module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    raise RuntimeError(f"runner_forbidden_import:{alias.name}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def registry_manifest(registry: dict[str, Any]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for row in registry.get("profiles", []):
        if not isinstance(row, dict):
            continue
        manifest.append({
            "profile_id": row.get("profile_id"),
            "profile_version": row.get("profile_version"),
            "profile_kind": row.get("profile_kind"),
            "prompt_version": row.get("prompt_version"),
            "skills": list(row.get("skills") or []),
            "enabled": row.get("enabled", True),
        })
    return manifest


def load_candidate_fixture(fixtures_dir: Path, profile_id: str, frame_id: str) -> dict[str, Any] | None:
    path = fixtures_dir / profile_id / f"{frame_id}.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture_invalid:{path}")
    return value


def build_normalized_candidate(
    *,
    fixture: dict[str, Any] | None,
    run_id: str,
    profile: dict[str, Any],
    envelope: dict[str, Any],
    gate: dict[str, Any],
    started_utc: str,
    finished_utc: str,
    latency_ms: int,
) -> dict[str, Any]:
    overlay = adapt_evaluation_output(raw=fixture, gate=gate)
    direction = overlay.get("direction")
    objections = []
    for objection in list((fixture or {}).get("objections") or []):
        preserved = copy.deepcopy(objection)
        if isinstance(preserved, dict):
            preserved.setdefault("source_profile_id", str(profile["profile_id"]))
        objections.append(preserved)
    return {
        "schema_version": "glitch.topstep.normalized_candidate.v1",
        "run_id": run_id,
        "profile_id": str(profile["profile_id"]),
        "profile_version": str(profile["profile_version"]),
        "invocation_id": str((fixture or {}).get("invocation_id") or uuid.uuid4()),
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope_hash(envelope),
        "state": overlay["state"],
        "comparability": overlay["comparability"],
        "profile_declared_state": overlay["profile_declared_state"],
        "profile_declared_direction": overlay["profile_declared_direction"],
        "capacity_gate_reason": overlay["capacity_gate_reason"],
        "instrument": str((fixture or {}).get("instrument") or envelope["instrument"]),
        "contract_id": (
            (fixture or {}).get("contract_id")
            or ((fixture or {}).get("contract", {}).get("id") if isinstance((fixture or {}).get("contract"), dict) else None)
            or ((envelope.get("contract") or {}).get("id") if isinstance(envelope.get("contract"), dict) else None)
        ),
        "contract_generation": (fixture or {}).get("contract_generation"),
        "quantity": (fixture or {}).get("quantity"),
        "prompt_version": profile.get("prompt_version"),
        "direction": direction,
        "thesis": overlay.get("thesis"),
        "thesis_source": overlay.get("thesis_source"),
        "evidence_refs": list((fixture or {}).get("evidence_refs") or []),
        "objections": objections,
        "entry": (fixture or {}).get("entry"),
        "entry_range": (fixture or {}).get("entry_range"),
        "stop": (fixture or {}).get("stop"),
        "target": (fixture or {}).get("target"),
        "target_absence_reason": (fixture or {}).get("target_absence_reason"),
        "horizon_bars": (fixture or {}).get("horizon_bars"),
        "invalidation": (fixture or {}).get("invalidation"),
        "uncertainties": list((fixture or {}).get("uncertainties") or gate.get("missing_required", [])),
        "forecast": (fixture or {}).get("forecast"),
        "completeness_used": gate["completeness_used"],
        "raw_status": overlay.get("raw_status"),
        "error_code": overlay.get("error_code"),
        "delayed": bool((fixture or {}).get("delayed") or (fixture or {}).get("result_delayed")),
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "latency_ms": latency_ms,
    }
