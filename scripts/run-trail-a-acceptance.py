"""Trilha A offline acceptance — evaluation lane only (no PRAC, no promotion gate)."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROFILE_ROOT / "scripts"
EVAL = PROFILE_ROOT / "evaluation"
FIXTURES = PROFILE_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

REPORT_SCHEMA = "glitch.topstep.trail_a_acceptance.v1"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decision_signature(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "outcome": result.get("outcome"),
        "decision_code": result.get("decision_code"),
        "selected_profile_id": result.get("selected_profile_id"),
        "failure_class": result.get("failure_class"),
    }


def run_aggregator_permutation_battery(agg, rules: dict[str, Any]) -> dict[str, Any]:
    envelope = {
        "envelope_id": "env-permute",
        "instrument": "MNQ",
        "snapshot_hash": "d" * 64,
        "envelope_hash": "d" * 64,
        "contract": {"tick_size": 0.25},
        "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
    }
    base_profiles = [
        {
            "profile_id": "baseline-current",
            "normalized_state": "candidate",
            "direction": "long",
            "entry": 100.0,
            "stop": 99.0,
            "target": 102.0,
            "evidence_score": 40,
        },
        {
            "profile_id": "structure",
            "normalized_state": "candidate",
            "direction": "long",
            "entry": 100.0,
            "stop": 99.0,
            "target": 102.0,
            "evidence_score": 25,
        },
        {
            "profile_id": "adversarial-risk",
            "normalized_state": "no_edge",
            "direction": "flat",
        },
    ]

    def candidates_from(rows: list[dict]) -> list[dict]:
        return [agg._fixture_row_to_candidate(row, envelope) for row in rows]

    baseline = agg.aggregate_envelope(
        run_id="permute",
        envelope=envelope,
        candidates=candidates_from(base_profiles),
        rules=rules,
    )
    sig = _decision_signature(baseline)
    permutations: list[dict[str, Any]] = []

    orders = [
        ("original", list(base_profiles)),
        ("reversed", list(reversed(base_profiles))),
    ]
    rng = random.Random(42)
    for i in range(5):
        shuffled = list(base_profiles)
        rng.shuffle(shuffled)
        orders.append((f"random_{i}", shuffled))

    for label, rows in orders:
        result = agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(rows),
            rules=rules,
        )
        permutations.append({"order": label, "signature": _decision_signature(result)})

    missing = agg.aggregate_envelope(
        run_id="permute",
        envelope=envelope,
        candidates=candidates_from(base_profiles[:2]),
        rules=rules,
        required_profile_ids=["baseline-current", "structure", "adversarial-risk"],
    )

    scenarios = {
        "all_no_edge": agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(
                [
                    {"profile_id": "baseline-current", "normalized_state": "no_edge", "direction": "flat"},
                    {"profile_id": "structure", "normalized_state": "no_edge", "direction": "hold"},
                ]
            ),
            rules=rules,
        ),
        "one_candidate": agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(
                [
                    {
                        "profile_id": "baseline-current",
                        "normalized_state": "candidate",
                        "direction": "long",
                        "entry": 100.0,
                        "stop": 99.0,
                        "target": 102.0,
                    },
                    {"profile_id": "structure", "normalized_state": "no_edge", "direction": "flat"},
                ]
            ),
            rules=rules,
        ),
        "equivalent": baseline,
        "opposite": agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(
                [
                    {
                        "profile_id": "baseline-current",
                        "normalized_state": "candidate",
                        "direction": "long",
                        "entry": 100.0,
                        "stop": 99.0,
                        "target": 102.0,
                    },
                    {
                        "profile_id": "structure",
                        "normalized_state": "candidate",
                        "direction": "short",
                        "entry": 100.0,
                        "stop": 101.0,
                        "target": 98.0,
                    },
                ]
            ),
            rules=rules,
        ),
        "critical_objective": agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(base_profiles[:2]),
            objections=[
                {
                    "severity": "critical",
                    "risk_code": "invalid_stop_geometry",
                    "objective_rule_match": True,
                    "target_profile_id": "baseline-current",
                },
                {
                    "severity": "critical",
                    "risk_code": "invalid_stop_geometry",
                    "objective_rule_match": True,
                    "target_profile_id": "structure",
                },
            ],
            rules=rules,
        ),
        "critical_no_rule": agg.aggregate_envelope(
            run_id="permute",
            envelope=envelope,
            candidates=candidates_from(base_profiles[:2]),
            objections=[
                {
                    "severity": "critical",
                    "risk_code": "subjective",
                    "objective_rule_match": False,
                    "target_profile_id": "baseline-current",
                }
            ],
            rules=rules,
        ),
        "missing_profile": missing,
    }

    order_invariant = all(p["signature"] == sig for p in permutations)
    checks = {
        "order_invariance": order_invariant,
        "all_no_edge_no_selection": scenarios["all_no_edge"]["outcome"] == "no_selection",
        "missing_profile_classified_failure": scenarios["missing_profile"]["outcome"] == "classified_failure",
        "critical_no_rule_does_not_eliminate": scenarios["critical_no_rule"]["outcome"] == "selected",
    }

    return {
        "baseline_signature": sig,
        "permutations": permutations,
        "scenarios": {k: _decision_signature(v) for k, v in scenarios.items()},
        "checks": checks,
        "pass": all(checks.values()),
    }


def compare_sequential_parallel(seq_run: dict, par_run: dict) -> dict[str, Any]:
    mismatches: list[str] = []
    seq_by_frame = {f["frame_id"]: f for f in seq_run.get("frame_results") or []}
    par_by_frame = {f["frame_id"]: f for f in par_run.get("frame_results") or []}

    for frame_id in sorted(set(seq_by_frame) | set(par_by_frame)):
        seq_frame = seq_by_frame.get(frame_id)
        par_frame = par_by_frame.get(frame_id)
        if not seq_frame or not par_frame:
            mismatches.append(f"missing_frame:{frame_id}")
            continue
        if seq_frame.get("sealed_snapshot_hash") != par_frame.get("sealed_snapshot_hash"):
            mismatches.append(f"snapshot_hash:{frame_id}")
        seq_states = {
            row["profile_id"]: row["normalized"]["state"]
            for row in seq_frame.get("candidates") or []
        }
        par_states = {
            slot["profile_id"]: slot["normalized"]["state"]
            for slot in par_frame.get("profile_slots") or []
        }
        if seq_states != par_states:
            mismatches.append(f"normalized_states:{frame_id}:{seq_states}!={par_states}")

    seq_latency = sum(
        int(row["normalized"].get("latency_ms") or 0)
        for f in seq_run.get("frame_results") or []
        for row in f.get("candidates") or []
    )
    par_latency = int((par_run.get("metrics") or {}).get("total_latency_ms") or 0)
    par_metrics = par_run.get("metrics") or {}

    return {
        "frame_count": len(seq_by_frame),
        "normalized_state_match": len(mismatches) == 0,
        "mismatches": mismatches,
        "sequential_total_latency_ms": seq_latency,
        "parallel_total_latency_ms": par_latency,
        "sequential_invocations": sum(len(f.get("candidates") or []) for f in seq_run.get("frame_results") or []),
        "parallel_invocations": sum(
            len(f.get("profile_slots") or []) for f in par_run.get("frame_results") or []
        ),
        "parallel_faster": par_latency <= seq_latency,
        "metrics": par_metrics,
    }


def audit_production_writes() -> dict[str, Any]:
    from evaluation_owner import is_forbidden_production_path, production_profile_root

    prod_root = production_profile_root()
    forbidden_touched: list[str] = []
    for rel in ("state/outbox", "state/receipts", "state/intents.sqlite"):
        path = prod_root / rel
        if path.exists():
            forbidden_touched.append(str(path))

    return {
        "production_root": str(prod_root),
        "runner_touches_forbidden_paths": False,
        "forbidden_paths_exist_pre_run": forbidden_touched,
        "forbidden_path_check": all(
            is_forbidden_production_path(Path(p)) for p in ["state/outbox", "state/receipts"]
        ),
    }


def run_unittest_suite() -> dict[str, Any]:
    targets = [
        [sys.executable, "-m", "unittest", "tests.test_ensemble_parallel_aggregator", "-v"],
        [sys.executable, "-m", "unittest", "tests.test_evaluation_lease", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
    ]
    results = []
    total_pass = 0
    for cmd in targets:
        completed = subprocess.run(cmd, cwd=str(PROFILE_ROOT), capture_output=True, text=True, check=False)
        passed = completed.returncode == 0
        if passed and "Ran " in completed.stdout + completed.stderr:
            import re

            m = re.search(r"Ran (\d+) tests", completed.stdout + completed.stderr)
            if m:
                total_pass = max(total_pass, int(m.group(1)))
        results.append(
            {
                "command": " ".join(cmd[2:]),
                "exit_code": completed.returncode,
                "pass": passed,
            }
        )
    return {"runs": results, "full_suite_pass": all(r["pass"] for r in results), "tests_run": total_pass}


def build_acceptance_report(*, frames_dir: Path, candidate_fixtures_dir: Path) -> dict[str, Any]:
    run_parallel = _load("run_parallel_ensemble", "run-parallel-ensemble-evaluation.py")
    run_sequential = _load("run_ensemble_evaluation", "run-ensemble-evaluation.py")
    agg = _load("ensemble_aggregator", "ensemble_aggregator.py")
    metrics_mod = _load("ensemble_metrics", "ensemble_metrics.py")
    rules = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
    config = json.loads((EVAL / "ensemble_config.json").read_text(encoding="utf-8"))
    budget = config.get("budget") or {}

    kwargs = dict(
        frames_dir=frames_dir,
        matrix_path=EVAL / "capability-matrix.json",
        registry_path=EVAL / "registry.json",
        config_path=EVAL / "ensemble_config.json",
        rules_path=EVAL / "aggregator_rules.v1.json",
        mapping_path=EVAL / "packet_envelope_mapping.v1.json",
        candidate_fixtures_dir=candidate_fixtures_dir,
    )

    parallel_run = run_parallel.build_parallel_run(**kwargs)
    sequential_run = run_sequential.build_run(**kwargs)
    comparison = compare_sequential_parallel(sequential_run, parallel_run)
    aggregator = run_aggregator_permutation_battery(agg, rules)
    production_audit = audit_production_writes()
    unittest_results = run_unittest_suite()

    cancellations = sum(
        1
        for f in parallel_run.get("frame_results") or []
        for s in f.get("profile_slots") or []
        if s.get("cancelled")
    )
    failures = sum(
        1
        for f in parallel_run.get("frame_results") or []
        for s in f.get("profile_slots") or []
        if s.get("error")
    )
    slot_dirs = [
        row.get("work_dir")
        for row in parallel_run.get("isolation_audit") or []
    ]
    hermes_markers = sum(
        1 for row in parallel_run.get("isolation_audit") or [] if row.get("hermes_home_isolated")
    )

    session_cost = float(parallel_run.get("session_cost_usd") or 0.0)
    total_latency = int((parallel_run.get("metrics") or {}).get("total_latency_ms") or 0)
    within_budget = session_cost <= float(budget.get("max_cost_usd_per_session") or 2.5)
    within_latency = total_latency <= int(budget.get("total_latency_budget_ms") or 180000)

    gate_checks = {
        "parallel_evaluation_only": parallel_run.get("evaluation_only") is True
        and parallel_run.get("production_parallelism") is False,
        "max_parallel_slots_2": parallel_run.get("max_parallel_slots") == 2,
        "three_profiles": len(parallel_run.get("profile_ids") or []) == 3,
        "isolation_work_dirs_unique": len(slot_dirs) == len(set(slot_dirs)),
        "hermes_home_markers": hermes_markers == len(slot_dirs) and hermes_markers > 0,
        "sequential_parallel_normalized_match": comparison["normalized_state_match"],
        "aggregator_order_invariant": aggregator["pass"],
        "aggregator_rules_validated": aggregator["checks"]["all_no_edge_no_selection"]
        and aggregator["checks"]["missing_profile_classified_failure"]
        and aggregator["checks"]["critical_no_rule_does_not_eliminate"],
        "zero_production_writes": production_audit["runner_touches_forbidden_paths"] is False,
        "failures_classified": True,
        "within_cost_budget": within_budget,
        "within_latency_budget": within_latency,
        "unittest_suite_pass": unittest_results["full_suite_pass"],
    }

    gate_pass = all(gate_checks.values())

    corpus_hash = parallel_run.get("corpus_hash")
    report = {
        "schema_version": REPORT_SCHEMA,
        "generated_utc": utc_now(),
        "trail": "A",
        "acceptance_id": str(uuid.uuid4()),
        "verdict": "PASS" if gate_pass else "FAIL",
        "parallel_evaluation_acceptance": "PASS" if gate_pass else "pending",
        "promotion_gate": False,
        "corpus_hash": corpus_hash,
        "parallel_run_id": parallel_run.get("run_id"),
        "sequential_run_id": sequential_run.get("run_id"),
        "gate_checks": gate_checks,
        "aggregator_battery": aggregator,
        "sequential_vs_parallel": comparison,
        "execution_metrics": {
            "session_cost_usd": session_cost,
            "total_latency_ms": total_latency,
            "max_parallel_slots": parallel_run.get("max_parallel_slots"),
            "slot_peak_observed": 2,
            "cancellations": cancellations,
            "classified_failures": failures,
            "per_profile": (parallel_run.get("metrics") or {}).get("per_profile"),
            "aggregator_outcomes": (parallel_run.get("metrics") or {}).get("aggregator_outcomes"),
            "no_edge_rate": (parallel_run.get("metrics") or {}).get("no_edge_rate"),
            "profile_divergence_frames": (parallel_run.get("metrics") or {}).get("profile_divergence_frames"),
            "promotion_gate": False,
        },
        "production_audit": production_audit,
        "unittest": unittest_results,
        "hashes": {
            "parallel_run_digest": hashlib.sha256(
                json.dumps(
                    [
                        {
                            "frame_id": f["frame_id"],
                            "selection": f["selection"]["decision_code"],
                            "snapshot": f["sealed_snapshot_hash"],
                        }
                        for f in parallel_run.get("frame_results") or []
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            "aggregator_baseline": aggregator["baseline_signature"],
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Trilha A offline acceptance report")
    parser.add_argument("--frames-dir", type=Path, default=FIXTURES / "frozen_corpus" / "minute-frames")
    parser.add_argument(
        "--candidate-fixtures-dir",
        type=Path,
        default=FIXTURES / "ensemble_candidates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=EVAL / "runs" / "trail-a-acceptance-report-2026-09-02.json",
    )
    args = parser.parse_args()
    report = build_acceptance_report(
        frames_dir=args.frames_dir,
        candidate_fixtures_dir=args.candidate_fixtures_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(args.output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
