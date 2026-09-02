"""Sequential offline-first ensemble evaluation runner (v1)."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import importlib.util

from ensemble_capacity_overlay import apply_capacity_gate_overlay
from ensemble_capability import capacity_gate
from ensemble_compare import compare_frame_profiles
from ensemble_validate import (
    validate_aggregator_rules,
    validate_capability_matrix,
    validate_ensemble_config,
    validate_evaluation_envelope,
    validate_normalized_candidate,
    validate_registry,
)
from ensemble_semantic import (
    validate_aggregator_rules_semantic,
    validate_capability_matrix_semantic,
    validate_candidate_semantic,
    validate_config_semantic,
    validate_envelope_semantic,
    validate_registry_semantic,
)
from ensemble_envelope import build_evaluation_envelope, envelope_hash

_SCRIPTS = Path(__file__).resolve().parent
_FROZEN_SPEC = importlib.util.spec_from_file_location(
    "run_frozen_cognition", _SCRIPTS / "run-frozen-cognition.py"
)
assert _FROZEN_SPEC and _FROZEN_SPEC.loader
_FROZEN = importlib.util.module_from_spec(_FROZEN_SPEC)
_FROZEN_SPEC.loader.exec_module(_FROZEN)
corpus_hash = _FROZEN.corpus_hash
load_frames = _FROZEN.load_frames

# ponytail: evaluation runner must not import production workflows or delivery paths.
FORBIDDEN_IMPORT_PREFIXES = (
    "workflows.",
    "run_topstep_cycle",
    "run-topstep-cycle",
    "intent_outbox",
    "model_owner_lock",
    "entry_delivery",
)

RUN_SCHEMA = "glitch.topstep.ensemble_run.v1"
PROFILE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROFILE_ROOT / "evaluation" / "capability-matrix.json"
DEFAULT_REGISTRY = PROFILE_ROOT / "evaluation" / "registry.json"
DEFAULT_CONFIG = PROFILE_ROOT / "evaluation" / "ensemble_config.json"
DEFAULT_RULES = PROFILE_ROOT / "evaluation" / "aggregator_rules.v1.json"
DEFAULT_MAPPING = PROFILE_ROOT / "evaluation" / "packet_envelope_mapping.v1.json"


def assert_runner_isolation() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
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
                if root in {"workflows", "intent_outbox", "model_owner_lock", "entry_delivery"}:
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
    overlay = apply_capacity_gate_overlay(fixture=fixture, gate=gate)
    direction = overlay.get("direction")
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
        "direction": direction,
        "thesis": (fixture or {}).get("thesis"),
        "evidence_refs": list((fixture or {}).get("evidence_refs") or []),
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
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "latency_ms": latency_ms,
    }


def build_run(
    *,
    frames_dir: Path,
    matrix_path: Path,
    registry_path: Path,
    config_path: Path,
    rules_path: Path,
    mapping_path: Path,
    candidate_fixtures_dir: Path | None,
) -> dict[str, Any]:
    assert_runner_isolation()
    matrix = read_json(matrix_path)
    registry = read_json(registry_path)
    config = read_json(config_path)
    rules = read_json(rules_path)
    mapping = read_json(mapping_path)
    validate_capability_matrix(matrix)
    validate_registry(registry)
    validate_ensemble_config(config)
    validate_aggregator_rules(rules)
    validate_capability_matrix_semantic(matrix)
    validate_registry_semantic(
        registry,
        matrix_version=str(matrix.get("matrix_version") or ""),
        config_version=str(config.get("config_version") or ""),
        rules_version=str(rules.get("rules_version") or ""),
    )
    validate_config_semantic(config, profile_count=len(registry.get("profiles", [])))
    validate_aggregator_rules_semantic(rules)

    frames = load_frames(frames_dir)
    run_id = str(uuid.uuid4())
    source_catalog = matrix.get("source_catalog")
    if not isinstance(source_catalog, dict):
        raise ValueError("source_catalog_missing")

    profiles = [row for row in registry["profiles"] if row.get("enabled", True)]
    frame_results: list[dict[str, Any]] = []
    profile_comparisons: list[dict[str, Any]] = []

    for item in frames:
        frame_id = str(item["minute_id"])
        packet = item["packet"]
        reference_utc = str(item["frame"].get("captured_utc") or utc_now())
        envelope = build_evaluation_envelope(
            packet=packet,
            source_catalog=source_catalog,
            reference_utc=reference_utc,
            validity_seconds=int(config.get("budget", {}).get("per_profile_timeout_ms", 35000) // 1000),
            frame_id=frame_id,
            corpus_ref=str(frames_dir),
            mapping=mapping,
        )
        validate_evaluation_envelope(envelope)
        validate_envelope_semantic(envelope, mapping)
        sealed_snapshot_hash = str(envelope["snapshot_hash"])
        if envelope["snapshot_hash"] != sealed_snapshot_hash:
            raise ValueError("snapshot_hash_mutated_at_seal")

        profile_rows: list[dict[str, Any]] = []
        gates: list[dict[str, Any]] = []
        for profile in profiles:
            profile_id = str(profile["profile_id"])
            gate = capacity_gate(envelope, profile_id, matrix)
            gates.append(gate)

            fixture: dict[str, Any] | None = None
            if candidate_fixtures_dir is not None:
                fixture = load_candidate_fixture(candidate_fixtures_dir, profile_id, frame_id)

            if fixture is None and gate["missing_required"]:
                now = utc_now()
                normalized = build_normalized_candidate(
                    fixture=None,
                    run_id=run_id,
                    profile=profile,
                    envelope=envelope,
                    gate=gate,
                    started_utc=now,
                    finished_utc=now,
                    latency_ms=0,
                )
                raw_profile_output = None
            elif fixture is not None:
                raw_profile_output = copy.deepcopy(fixture)
                normalized = build_normalized_candidate(
                    fixture=fixture,
                    run_id=run_id,
                    profile=profile,
                    envelope=envelope,
                    gate=gate,
                    started_utc=utc_now(),
                    finished_utc=utc_now(),
                    latency_ms=int(fixture.get("latency_ms") or 1),
                )
            else:
                raise ValueError(f"candidate_fixture_required:{profile_id}:{frame_id}")

            validate_normalized_candidate(normalized)
            validate_candidate_semantic(normalized, envelope=envelope)
            profile_rows.append({
                "profile_id": profile_id,
                "prompt_version": profile.get("prompt_version"),
                "skills": list(profile.get("skills") or []),
                "raw_profile_output": raw_profile_output,
                "normalized": normalized,
            })

        if envelope["snapshot_hash"] != sealed_snapshot_hash:
            raise ValueError("snapshot_hash_mutated_after_profiles")

        comparison = compare_frame_profiles(
            frame_id=frame_id,
            candidates=profile_rows,
            capacity_gates=gates,
        )
        profile_comparisons.append(comparison)

        frame_results.append({
            "frame_id": frame_id,
            "sealed_snapshot_hash": sealed_snapshot_hash,
            "envelope": envelope,
            "envelope_hash": envelope_hash(envelope),
            "capacity_gates": gates,
            "candidates": profile_rows,
        })

    return {
        "schema_version": RUN_SCHEMA,
        "evaluation_only": True,
        "armed_promotion_allowed": False,
        "run_id": run_id,
        "runner_version": "2026-09-01-v2-sequential-offline",
        "corpus_hash": corpus_hash(frames_dir),
        "profile_ids": [str(row["profile_id"]) for row in profiles],
        "registry_manifest": registry_manifest(registry),
        "matrix_version": matrix.get("matrix_version"),
        "registry_version": registry.get("registry_version"),
        "config_version": config.get("config_version"),
        "aggregator_rules_version": rules.get("rules_version"),
        "mapping_version": mapping.get("mapping_version"),
        "profile_comparisons": profile_comparisons,
        "frame_results": frame_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline sequential ensemble evaluation (v1).")
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--candidate-fixtures-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run = build_run(
        frames_dir=args.frames_dir,
        matrix_path=args.matrix,
        registry_path=args.registry,
        config_path=args.config,
        rules_path=args.rules,
        mapping_path=args.mapping,
        candidate_fixtures_dir=args.candidate_fixtures_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
