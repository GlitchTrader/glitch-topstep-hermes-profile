"""Trilha A — parallel live Hermes evaluation (evaluation lane; requires --authorize)."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import read_json  # noqa: E402
from ensemble_aggregator import aggregate_envelope  # noqa: E402
from ensemble_envelope_seal import (  # noqa: E402
    seal_envelope_from_pin,
    seal_envelope_from_run_config,
    sealed_envelope_identity,
)
from ensemble_metrics import compute_ensemble_metrics  # noqa: E402
from evaluation_cognitive_replay import (  # noqa: E402
    operational_artifact_snapshot,
    run_minimal_cognitive_replay,
)
from evaluation_lease import ProductionEvaluationLease  # noqa: E402
from evaluation_owner import (  # noqa: E402
    bootstrap_evaluation_hermes_home,
    cognitive_replay_controlled_scope,
    ensure_evaluation_auth_ready,
    evaluation_hermes_home,
    load_evaluation_budget,
    production_state_root,
)

import importlib.util

_PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "run_trail_a_real_preflight", SCRIPTS / "run-trail-a-real-preflight.py"
)
assert _PREFLIGHT_SPEC and _PREFLIGHT_SPEC.loader
_PREFLIGHT = importlib.util.module_from_spec(_PREFLIGHT_SPEC)
sys.modules["run_trail_a_real_preflight"] = _PREFLIGHT
_PREFLIGHT_SPEC.loader.exec_module(_PREFLIGHT)
run_trail_a_real_preflight = _PREFLIGHT.run_trail_a_real_preflight
is_multi_envelope_config = _PREFLIGHT.is_multi_envelope_config

RUN_SCHEMA = "glitch.topstep.trail_a_parallel_live_run.v1"
MULTI_RUN_SCHEMA = "glitch.topstep.trail_a_multi_envelope_live_run.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "trail-a-real-run-config.v1.json"
DEFAULT_SCENARIOS = REPO / "evaluation" / "trail-a-real-scenarios.v1.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _profile_worker(
    *,
    profile_id: str,
    frame_path: Path,
    run_id: str,
    frame_id: str,
    repo: Path,
    runs_dir: Path,
    session_cost_lock: threading.Lock,
    session_cost: list[float],
    sealed_envelope: dict[str, Any],
) -> dict[str, Any]:
    with cognitive_replay_controlled_scope():
        invocation_run_id = f"{run_id}-{profile_id}-{frame_id}"
        artifact_path = runs_dir / f"{invocation_run_id}.json"
        with session_cost_lock:
            cost_so_far = session_cost[0]
        artifact = run_minimal_cognitive_replay(
            frame_path=frame_path,
            profile_id=profile_id,
            run_id=invocation_run_id,
            repo_root=repo,
            output_path=artifact_path,
            session_cost_usd_so_far=cost_so_far,
            sealed_envelope=sealed_envelope,
        )
        with session_cost_lock:
            session_cost[0] += float(artifact.get("session_cost_usd") or artifact.get("cost_usd") or 0.0)
        return {
            "profile_id": profile_id,
            "invocation_id": artifact.get("invocation_id"),
            "artifact_path": str(artifact_path),
            "artifact": artifact,
            "work_dir": str(artifact.get("state_root") or ""),
        }


def _execute_envelope_frame(
    *,
    run_id: str,
    frame_id: str,
    scenario_id: str,
    frame_path: Path,
    profiles: list[str],
    sealed_envelope: dict[str, Any],
    sealed_identity: dict[str, Any],
    max_slots: int,
    max_cost: float,
    rules: dict[str, Any],
    runs_dir: Path,
    repo: Path,
    prod_state: Path,
    lease: ProductionEvaluationLease,
    session_cost: list[float],
    cost_lock: threading.Lock,
) -> dict[str, Any] | dict[str, Any]:
    prod_before = operational_artifact_snapshot(prod_state)
    profile_slots: list[dict[str, Any]] = []
    stop = threading.Event()

    lease.renew(invocation_id=f"eval-{run_id}-{frame_id}")
    with ThreadPoolExecutor(max_workers=max_slots) as pool:
        futures = {
            pool.submit(
                _profile_worker,
                profile_id=pid,
                frame_path=frame_path,
                run_id=run_id,
                frame_id=frame_id,
                repo=repo,
                runs_dir=runs_dir,
                session_cost_lock=cost_lock,
                session_cost=session_cost,
                sealed_envelope=sealed_envelope,
            ): pid
            for pid in profiles
        }
        for future in as_completed(futures):
            if stop.is_set():
                continue
            pid = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                stop.set()
                return {
                    "status": "failed",
                    "reason": f"profile_error:{scenario_id}:{pid}:{exc}",
                    "scenario_id": scenario_id,
                    "frame_id": frame_id,
                }
            art = row.get("artifact") or {}
            if art.get("status") != "completed":
                return {
                    "status": "failed",
                    "reason": f"profile_incomplete:{scenario_id}:{pid}",
                    "scenario_id": scenario_id,
                    "frame_id": frame_id,
                    "profile_slots": profile_slots + [row],
                }
            profile_slots.append(row)
            if session_cost[0] > max_cost:
                stop.set()
                return {
                    "status": "failed",
                    "reason": "cost_budget_exceeded",
                    "scenario_id": scenario_id,
                    "session_cost_usd": session_cost[0],
                }

    prod_after = operational_artifact_snapshot(prod_state)
    if prod_before != prod_after:
        return {
            "status": "failed",
            "reason": "production_artifact_mutation",
            "scenario_id": scenario_id,
            "frame_id": frame_id,
        }

    normalized = []
    for slot in sorted(profile_slots, key=lambda r: str(r.get("profile_id"))):
        norm = (slot.get("artifact") or {}).get("normalized")
        if norm:
            normalized.append(norm)

    envelope_for_agg = {
        "envelope_id": sealed_identity["envelope_id"],
        "snapshot_hash": sealed_identity["snapshot_hash"],
        "envelope_hash": sealed_identity["envelope_hash"],
        "instrument": sealed_identity["instrument"],
    }
    selection = aggregate_envelope(
        run_id=run_id,
        envelope=envelope_for_agg,
        candidates=normalized,
        objections=[],
        rules=rules,
    )

    agg_ok = selection.get("outcome") in {"selected", "no_selection"}
    candidate_hashes = {str(c.get("envelope_hash") or "") for c in normalized}
    candidate_hashes.discard("")
    identity_ok = len(candidate_hashes) == 1 and sealed_identity["envelope_hash"] in candidate_hashes

    return {
        "status": "completed" if agg_ok and identity_ok else "failed",
        "reason": None if agg_ok and identity_ok else "aggregator_or_identity_failed",
        "scenario_id": scenario_id,
        "frame_id": frame_id,
        "sealed_snapshot_hash": sealed_identity["snapshot_hash"],
        "sealed_envelope_hash": sealed_identity["envelope_hash"],
        "sealed_validity_seconds": sealed_identity.get("validity_seconds"),
        "profile_slots": profile_slots,
        "selection": selection,
        "identity_ok": identity_ok,
        "aggregator_ok": agg_ok,
    }


def run_trail_a_parallel_live(
    *,
    run_id: str,
    authorize: bool,
    config_path: Path = DEFAULT_CONFIG,
    scenarios_path: Path = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    if not authorize:
        preflight = run_trail_a_real_preflight(run_id=run_id, config_path=config_path, scenarios_path=scenarios_path)
        return {
            "schema_version": RUN_SCHEMA,
            "status": "awaiting_human_authorization",
            "run_id": run_id,
            "evaluation_only": True,
            "preflight": preflight,
            "message": "Re-run with --authorize after human approval",
        }

    preflight = run_trail_a_real_preflight(run_id=run_id, config_path=config_path, scenarios_path=scenarios_path)
    if preflight.get("verdict") != "PASS":
        return {
            "schema_version": RUN_SCHEMA,
            "status": "blocked",
            "reason": "preflight_failed",
            "preflight": preflight,
        }

    config = read_json(config_path)
    scenarios = read_json(scenarios_path)
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    budget = load_evaluation_budget(REPO / "evaluation" / "ensemble_config.json")
    max_slots = int((config.get("budget") or {}).get("max_parallel_slots") or 2)
    max_cost = float((config.get("budget") or {}).get("max_cost_usd_per_session") or 2.5)
    profiles = list(scenarios.get("profiles") or [])
    multi = is_multi_envelope_config(config)
    runs_dir = REPO / "evaluation" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_evaluation_hermes_home()
    auth_ok, auth_err = ensure_evaluation_auth_ready(evaluation_hermes_home())
    if not auth_ok:
        return {"schema_version": RUN_SCHEMA, "status": "blocked", "reason": auth_err}

    prod_state = production_state_root()
    lease_ttl = max(60, int(budget.get("total_timeout_ms", 120000)) // 1000 + 120)
    lease = ProductionEvaluationLease(
        production_state=prod_state,
        run_id=run_id,
        invocation_id=f"eval-session-{run_id}",
        ttl_seconds=lease_ttl,
    )
    if not lease.acquire():
        return {"schema_version": RUN_SCHEMA, "status": "blocked", "reason": "evaluation_lease_conflict"}

    session_cost = [0.0]
    cost_lock = threading.Lock()

    try:
        if multi:
            frame_results: list[dict[str, Any]] = []
            for pin in config.get("envelopes") or []:
                frame_path = REPO / str(pin.get("frame_path") or "")
                frame_id = str(pin.get("frame_id") or "")
                scenario_id = str(pin.get("scenario_id") or frame_id)
                sealed_envelope = seal_envelope_from_pin(
                    envelope_pin=pin,
                    config=config,
                    matrix=matrix,
                    mapping=mapping,
                    repo=REPO,
                )
                sealed_identity = sealed_envelope_identity(sealed_envelope)
                frame_result = _execute_envelope_frame(
                    run_id=run_id,
                    frame_id=frame_id,
                    scenario_id=scenario_id,
                    frame_path=frame_path,
                    profiles=profiles,
                    sealed_envelope=sealed_envelope,
                    sealed_identity=sealed_identity,
                    max_slots=max_slots,
                    max_cost=max_cost,
                    rules=rules,
                    runs_dir=runs_dir,
                    repo=REPO,
                    prod_state=prod_state,
                    lease=lease,
                    session_cost=session_cost,
                    cost_lock=cost_lock,
                )
                frame_results.append(frame_result)
                if frame_result.get("status") != "completed":
                    return {
                        "schema_version": MULTI_RUN_SCHEMA,
                        "status": "failed",
                        "evaluation_only": True,
                        "run_id": run_id,
                        "reason": frame_result.get("reason"),
                        "failed_at": scenario_id,
                        "frame_results": frame_results,
                        "session_cost_usd": round(session_cost[0], 6),
                    }

            run_doc = {
                "schema_version": MULTI_RUN_SCHEMA,
                "status": "completed",
                "evaluation_only": True,
                "production_parallelism": False,
                "cognitive_replay": True,
                "multi_envelope": True,
                "run_id": run_id,
                "authorized_utc": utc_now(),
                "max_parallel_slots": max_slots,
                "envelope_count": len(frame_results),
                "frame_results": frame_results,
                "session_cost_usd": round(session_cost[0], 6),
                "production_paths_untouched": True,
                "trail_a_gate": {
                    "parallel_evaluation_real": "PASS",
                    "aggregator_offline_real": "PASS",
                    "parallel_evaluation_acceptance": "PASS",
                },
            }
            run_doc["metrics"] = compute_ensemble_metrics(
                {
                    "session_cost_usd": session_cost[0],
                    "frame_results": [
                        {
                            "profile_slots": [
                                {
                                    "profile_id": s.get("profile_id"),
                                    "latency_ms": (s.get("artifact") or {}).get("latency_ms", 0),
                                    "estimated_cost_usd": (s.get("artifact") or {}).get("cost_usd", 0),
                                    "normalized": (s.get("artifact") or {}).get("normalized"),
                                }
                                for s in fr.get("profile_slots") or []
                            ],
                            "selection": fr.get("selection"),
                        }
                        for fr in frame_results
                    ],
                }
            )
            return run_doc

        scenario = (scenarios.get("scenarios") or [{}])[0]
        frame_id = str(scenario["frame_id"])
        corpus_root = REPO / str(scenarios.get("corpus_root") or "")
        frame_path = corpus_root / "minute-frames" / f"{frame_id}.json"
        sealed_envelope = seal_envelope_from_run_config(
            config=config,
            matrix=matrix,
            mapping=mapping,
            repo=REPO,
        )
        sealed_identity = sealed_envelope_identity(sealed_envelope)
        frame_result = _execute_envelope_frame(
            run_id=run_id,
            frame_id=frame_id,
            scenario_id=str(scenario.get("scenario_id") or frame_id),
            frame_path=frame_path,
            profiles=profiles,
            sealed_envelope=sealed_envelope,
            sealed_identity=sealed_identity,
            max_slots=max_slots,
            max_cost=max_cost,
            rules=rules,
            runs_dir=runs_dir,
            repo=REPO,
            prod_state=prod_state,
            lease=lease,
            session_cost=session_cost,
            cost_lock=cost_lock,
        )
        if frame_result.get("status") != "completed":
            return {
                "schema_version": RUN_SCHEMA,
                "status": "failed",
                "reason": frame_result.get("reason"),
                "run_id": run_id,
                "frame_result": frame_result,
            }

        profile_slots = frame_result["profile_slots"]
        selection = frame_result["selection"]
        run_doc = {
            "schema_version": RUN_SCHEMA,
            "status": "completed",
            "evaluation_only": True,
            "production_parallelism": False,
            "cognitive_replay": True,
            "run_id": run_id,
            "authorized_utc": utc_now(),
            "max_parallel_slots": max_slots,
            "frame_id": frame_id,
            "sealed_snapshot_hash": sealed_identity["snapshot_hash"],
            "sealed_envelope_hash": sealed_identity["envelope_hash"],
            "envelope_hash": sealed_identity["envelope_hash"],
            "sealed_validity_seconds": sealed_identity.get("validity_seconds"),
            "profile_slots": profile_slots,
            "selection": selection,
            "session_cost_usd": round(session_cost[0], 6),
            "production_paths_untouched": True,
        }
        run_doc["metrics"] = compute_ensemble_metrics(
            {
                "session_cost_usd": session_cost[0],
                "frame_results": [
                    {
                        "profile_slots": [
                            {
                                "profile_id": s.get("profile_id"),
                                "latency_ms": (s.get("artifact") or {}).get("latency_ms", 0),
                                "estimated_cost_usd": (s.get("artifact") or {}).get("cost_usd", 0),
                                "normalized": (s.get("artifact") or {}).get("normalized"),
                            }
                            for s in profile_slots
                        ],
                        "selection": selection,
                    }
                ],
            }
        )
        return run_doc
    finally:
        lease.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Trilha A parallel live Hermes evaluation")
    parser.add_argument("--run-id", default="trail-a-real-2026-09-02")
    parser.add_argument("--authorize", action="store_true", help="Human authorization required for Hermes invoke")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    result = run_trail_a_parallel_live(
        run_id=args.run_id,
        authorize=args.authorize,
        config_path=args.config,
        scenarios_path=args.scenarios,
    )
    output = args.output or (REPO / "evaluation" / "runs" / f"{args.run_id}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "output": str(output)}, indent=2))
    if result.get("status") in {"failed", "blocked"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
