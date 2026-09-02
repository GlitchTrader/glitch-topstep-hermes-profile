"""Parallel offline ensemble evaluation runner (evaluation lane only)."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import uuid
from pathlib import Path
from typing import Any

from ensemble_aggregator import aggregate_envelope
from ensemble_capability import capacity_gate
from ensemble_envelope import envelope_hash
from ensemble_envelope_seal import envelope_validity_seconds, seal_evaluation_envelope_from_frame
from ensemble_metrics import compute_ensemble_metrics
from ensemble_parallel_runner import cleanup_work_dirs, run_profiles_parallel
from ensemble_validate import (
    validate_aggregator_rules,
    validate_capability_matrix,
    validate_ensemble_config,
    validate_evaluation_envelope,
    validate_normalized_candidate,
    validate_registry,
)

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent

_SEQ_SPEC = importlib.util.spec_from_file_location(
    "run_ensemble_evaluation", _SCRIPTS / "run-ensemble-evaluation.py"
)
assert _SEQ_SPEC and _SEQ_SPEC.loader
_SEQ = importlib.util.module_from_spec(_SEQ_SPEC)
_SEQ_SPEC.loader.exec_module(_SEQ)

_FROZEN_SPEC = importlib.util.spec_from_file_location(
    "run_frozen_cognition", _SCRIPTS / "run-frozen-cognition.py"
)
assert _FROZEN_SPEC and _FROZEN_SPEC.loader
_FROZEN = importlib.util.module_from_spec(_FROZEN_SPEC)
_FROZEN_SPEC.loader.exec_module(_FROZEN)

RUN_SCHEMA = "glitch.topstep.ensemble_parallel_run.v1"
DEFAULT_MATRIX = _REPO / "evaluation" / "capability-matrix.json"
DEFAULT_REGISTRY = _REPO / "evaluation" / "registry.json"
DEFAULT_CONFIG = _REPO / "evaluation" / "ensemble_config.json"
DEFAULT_RULES = _REPO / "evaluation" / "aggregator_rules.v1.json"
DEFAULT_MAPPING = _REPO / "evaluation" / "packet_envelope_mapping.v1.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parallel_run(
    *,
    frames_dir: Path,
    matrix_path: Path,
    registry_path: Path,
    config_path: Path,
    rules_path: Path,
    mapping_path: Path,
    candidate_fixtures_dir: Path,
) -> dict[str, Any]:
    _SEQ.assert_runner_isolation()
    matrix = read_json(matrix_path)
    registry = read_json(registry_path)
    config = read_json(config_path)
    rules = read_json(rules_path)
    mapping = read_json(mapping_path)
    validate_capability_matrix(matrix)
    validate_registry(registry)
    validate_ensemble_config(config)
    validate_aggregator_rules(rules)

    frames = _FROZEN.load_frames(frames_dir)
    run_id = str(uuid.uuid4())
    profiles = [row for row in registry["profiles"] if row.get("enabled", True)]
    budget = config.get("budget") or {}
    max_parallel = int(budget.get("max_parallel_slots") or 2)
    max_cost = float(budget.get("max_cost_usd_per_session") or 2.5)
    per_profile_timeout = int(budget.get("per_profile_timeout_ms") or 35000)
    total_timeout = int(budget.get("total_timeout_ms") or 120000)
    source_catalog = matrix["source_catalog"]

    def loader(profile_id: str, frame_id: str) -> dict[str, Any] | None:
        return _SEQ.load_candidate_fixture(candidate_fixtures_dir, profile_id, frame_id)

    def builder(**kwargs: Any) -> dict[str, Any]:
        return _SEQ.build_normalized_candidate(**kwargs)

    frame_results: list[dict[str, Any]] = []
    session_cost = 0.0

    for item in frames:
        frame_id = str(item["minute_id"])
        frame_doc = item["frame"]
        envelope = seal_evaluation_envelope_from_frame(
            frame=frame_doc,
            source_catalog=source_catalog,
            mapping=mapping,
            validity_seconds=envelope_validity_seconds(budget=budget),
            frame_path=str(frames_dir),
        )
        validate_evaluation_envelope(envelope)
        sealed = str(envelope["snapshot_hash"])
        gates = {str(p["profile_id"]): capacity_gate(envelope, str(p["profile_id"]), matrix) for p in profiles}

        slot_results = run_profiles_parallel(
            profiles=profiles,
            frame_id=frame_id,
            run_id=run_id,
            envelope=envelope,
            gates_by_profile=gates,
            loader=loader,
            builder=builder,
            max_parallel_slots=max_parallel,
            max_cost_usd=max_cost,
            per_profile_timeout_ms=per_profile_timeout,
            total_timeout_ms=total_timeout,
        )

        normalized_candidates = []
        profile_rows = []
        for slot in slot_results:
            session_cost += slot.estimated_cost_usd
            if slot.normalized is None:
                continue
            validate_normalized_candidate(slot.normalized)
            normalized_candidates.append(slot.normalized)
            profile_rows.append(
                {
                    "profile_id": slot.profile_id,
                    "invocation_id": slot.invocation_id,
                    "work_dir": slot.work_dir,
                    "latency_ms": slot.latency_ms,
                    "estimated_cost_usd": slot.estimated_cost_usd,
                    "cancelled": slot.cancelled,
                    "error": slot.error,
                    "raw_profile_output": copy.deepcopy(slot.raw_profile_output),
                    "normalized": slot.normalized,
                }
            )

        if envelope["snapshot_hash"] != sealed:
            raise ValueError("snapshot_hash_mutated_after_parallel_profiles")

        selection = aggregate_envelope(
            run_id=run_id,
            envelope={**envelope, "envelope_hash": envelope_hash(envelope)},
            candidates=normalized_candidates,
            objections=[],
            rules=rules,
        )

        frame_results.append(
            {
                "frame_id": frame_id,
                "sealed_snapshot_hash": sealed,
                "envelope_hash": envelope_hash(envelope),
                "profile_slots": profile_rows,
                "selection": selection,
            }
        )

    isolation_audit = []
    for frame in frame_results:
        for slot in frame.get("profile_slots") or []:
            work_dir = Path(str(slot.get("work_dir") or ""))
            marker = work_dir / "HERMES_HOME_ISOLATED"
            isolation_audit.append(
                {
                    "profile_id": slot.get("profile_id"),
                    "invocation_id": slot.get("invocation_id"),
                    "work_dir": str(work_dir),
                    "hermes_home_isolated": marker.is_file(),
                }
            )

    cleanup_work_dirs(run_id)
    run_doc = {
        "schema_version": RUN_SCHEMA,
        "evaluation_only": True,
        "armed_promotion_allowed": False,
        "production_parallelism": False,
        "run_id": run_id,
        "runner_version": "2026-09-02-v1-parallel-offline",
        "max_parallel_slots": max_parallel,
        "corpus_hash": _FROZEN.corpus_hash(frames_dir),
        "profile_ids": [str(p["profile_id"]) for p in profiles],
        "matrix_version": matrix.get("matrix_version"),
        "registry_version": registry.get("registry_version"),
        "config_version": config.get("config_version"),
        "aggregator_rules_version": rules.get("rules_version"),
        "session_cost_usd": round(session_cost, 6),
        "isolation_audit": isolation_audit,
        "frame_results": frame_results,
    }
    run_doc["metrics"] = compute_ensemble_metrics(run_doc)
    return run_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel offline ensemble evaluation")
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--candidate-fixtures-dir", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run = build_parallel_run(
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
