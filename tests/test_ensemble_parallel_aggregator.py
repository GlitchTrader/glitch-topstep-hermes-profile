"""Tests for parallel ensemble runner, deterministic aggregator, and metrics."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


AGG = _load("ensemble_aggregator", "ensemble_aggregator.py")
PARALLEL = _load("ensemble_parallel_runner", "ensemble_parallel_runner.py")
METRICS = _load("ensemble_metrics", "ensemble_metrics.py")
RUN_PARALLEL = _load("run_parallel_ensemble", "run-parallel-ensemble-evaluation.py")
RULES = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
FIXTURE_CASES = json.loads(
    (EVAL / "fixtures" / "aggregator_decision_cases.v1.json").read_text(encoding="utf-8")
)


class AggregatorFixtureTests(unittest.TestCase):
    def test_all_spec_fixtures_match_expected(self) -> None:
        for case in FIXTURE_CASES["cases"]:
            with self.subTest(case_id=case["case_id"]):
                result = AGG.aggregate_fixture_case(case, rules=RULES)
                expected = case["expected"]
                self.assertEqual(result["outcome"], expected["result"])
                self.assertEqual(result["decision_code"], expected["decision_code"])
                if expected.get("selected_profile_id") is not None:
                    self.assertEqual(result["selected_profile_id"], expected["selected_profile_id"])
                for token in expected.get("decision_trace_contains") or []:
                    self.assertTrue(
                        any(token in step for step in result["decision_trace"]),
                        msg=f"missing trace token {token} in {result['decision_trace']}",
                    )

    def test_determinism_same_input_same_output(self) -> None:
        case = FIXTURE_CASES["cases"][0]
        a = AGG.aggregate_fixture_case(case, rules=RULES, run_id="determinism")
        b = AGG.aggregate_fixture_case(case, rules=RULES, run_id="determinism")
        self.assertEqual(a["outcome"], b["outcome"])
        self.assertEqual(a["decision_code"], b["decision_code"])
        self.assertEqual(a["selected_profile_id"], b["selected_profile_id"])


class AggregatorScenarioTests(unittest.TestCase):
    def _aggregate_profiles(self, profiles: list[dict], objections: list | None = None) -> dict:
        envelope = {
            "envelope_id": "env-test",
            "instrument": "MNQ",
            "snapshot_hash": "a" * 64,
            "envelope_hash": "a" * 64,
            "contract": {"tick_size": 0.25},
            "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
        }
        candidates = [AGG._fixture_row_to_candidate(p, envelope) for p in profiles]
        return AGG.aggregate_envelope(
            run_id="scenario",
            envelope=envelope,
            candidates=candidates,
            objections=objections or [],
            rules=RULES,
        )

    def test_all_no_edge_yields_no_selection(self) -> None:
        result = self._aggregate_profiles(
            [
                {"profile_id": "baseline-current", "normalized_state": "no_edge", "direction": "flat"},
                {"profile_id": "structure", "normalized_state": "no_edge", "direction": "hold"},
            ]
        )
        self.assertEqual(result["outcome"], "no_selection")
        self.assertEqual(result["decision_code"], "ENSEMBLE_UNANIMOUS_ABSTENTION")

    def test_one_candidate_others_abstain_category_divergence(self) -> None:
        result = self._aggregate_profiles(
            [
                {
                    "profile_id": "baseline-current",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 40,
                },
                {"profile_id": "structure", "normalized_state": "no_edge", "direction": "flat"},
            ]
        )
        self.assertEqual(result["decision_code"], "ENSEMBLE_CATEGORY_DIVERGENCE")

    def test_equivalent_candidates_evidence_score_win(self) -> None:
        result = self._aggregate_profiles(
            [
                {
                    "profile_id": "baseline-current",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 50,
                },
                {
                    "profile_id": "structure",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 20,
                },
            ]
        )
        self.assertEqual(result["outcome"], "selected")
        self.assertEqual(result["selected_profile_id"], "baseline-current")

    def test_opposite_directions_conflict(self) -> None:
        result = self._aggregate_profiles(
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
        )
        self.assertEqual(result["decision_code"], "DIRECTION_CONFLICT")

    def test_timeout_is_not_abstention(self) -> None:
        result = self._aggregate_profiles(
            [{"profile_id": "baseline-current", "normalized_state": "timeout"}],
        )
        self.assertNotEqual(result["decision_code"], "ENSEMBLE_UNANIMOUS_ABSTENTION")

    def test_missing_required_not_counted_as_no_edge(self) -> None:
        result = self._aggregate_profiles(
            [
                {
                    "profile_id": "baseline-current",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                },
                {"profile_id": "structure", "normalized_state": "missing_required_evidence"},
            ]
        )
        self.assertEqual(result["decision_code"], "INSUFFICIENT_ENSEMBLE_AGREEMENT")
        self.assertIn("MISSING_REQUIRED_EVIDENCE", result["decision_trace"])

    def test_adversarial_critical_objective_eliminates(self) -> None:
        result = self._aggregate_profiles(
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
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                },
            ],
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
        )
        self.assertEqual(result["decision_code"], "ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION")

    def test_adversarial_critical_without_rule_downgrades(self) -> None:
        result = self._aggregate_profiles(
            [
                {
                    "profile_id": "baseline-current",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 30,
                },
                {
                    "profile_id": "structure",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 30,
                },
            ],
            objections=[
                {
                    "severity": "critical",
                    "risk_code": "subjective",
                    "objective_rule_match": False,
                    "target_profile_id": "baseline-current",
                }
            ],
        )
        self.assertEqual(result["outcome"], "selected")
        self.assertEqual(result["decision_code"], "ADVERSARIAL_CRITICAL_DOWNGRADED")

    def test_envelope_hash_divergence_classified_failure(self) -> None:
        envelope = {
            "envelope_id": "env",
            "instrument": "MNQ",
            "snapshot_hash": "b" * 64,
            "envelope_hash": "b" * 64,
            "contract": {"tick_size": 0.25},
            "packet": {"market": {"last": 100.0}},
        }
        result = AGG.aggregate_envelope(
            run_id="x",
            envelope=envelope,
            candidates=[
                {
                    "profile_id": "baseline-current",
                    "state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "envelope_hash": "a" * 64,
                }
            ],
            rules=RULES,
        )
        self.assertEqual(result["outcome"], "classified_failure")
        self.assertEqual(result["failure_class"], "snapshot_divergence")

    def test_missing_profile_classified_failure(self) -> None:
        result = AGG.aggregate_envelope(
            run_id="missing",
            envelope={
                "envelope_id": "env",
                "instrument": "MNQ",
                "snapshot_hash": "c" * 64,
                "envelope_hash": "c" * 64,
                "contract": {"tick_size": 0.25},
                "packet": {"market": {"last": 100.0}},
            },
            candidates=[],
            rules=RULES,
            required_profile_ids=["baseline-current", "structure"],
        )
        self.assertEqual(result["outcome"], "classified_failure")
        self.assertEqual(result["decision_code"], "PROFILE_MISSING")

    def test_critical_without_rule_does_not_eliminate_candidate(self) -> None:
        result = self._aggregate_profiles(
            [
                {
                    "profile_id": "baseline-current",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 30,
                },
                {
                    "profile_id": "structure",
                    "normalized_state": "candidate",
                    "direction": "long",
                    "entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "evidence_score": 20,
                },
            ],
            objections=[
                {
                    "severity": "critical",
                    "risk_code": "narrative",
                    "objective_rule_match": False,
                    "target_profile_id": "baseline-current",
                }
            ],
        )
        self.assertEqual(result["outcome"], "selected")
        self.assertEqual(result["selected_profile_id"], "baseline-current")


class AggregatorOrderInvarianceTests(unittest.TestCase):
    def _rows(self) -> list[dict]:
        return [
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
            {"profile_id": "adversarial-risk", "normalized_state": "no_edge", "direction": "flat"},
        ]

    def _aggregate(self, rows: list[dict]) -> dict:
        envelope = {
            "envelope_id": "env-order",
            "instrument": "MNQ",
            "snapshot_hash": "9" * 64,
            "envelope_hash": "9" * 64,
            "contract": {"tick_size": 0.25},
            "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
        }
        candidates = [AGG._fixture_row_to_candidate(r, envelope) for r in rows]
        return AGG.aggregate_envelope(run_id="order", envelope=envelope, candidates=candidates, rules=RULES)

    def test_order_permutations_same_decision(self) -> None:
        import random

        rows = self._rows()
        baseline = self._aggregate(rows)
        sig = (baseline["outcome"], baseline["decision_code"], baseline.get("selected_profile_id"))
        rng = random.Random(7)
        for _ in range(10):
            shuffled = list(rows)
            rng.shuffle(shuffled)
            result = self._aggregate(shuffled)
            self.assertEqual(
                (result["outcome"], result["decision_code"], result.get("selected_profile_id")),
                sig,
            )

    def test_reversed_order_same_decision(self) -> None:
        rows = self._rows()
        a = self._aggregate(rows)
        b = self._aggregate(list(reversed(rows)))
        self.assertEqual(a["decision_code"], b["decision_code"])
        self.assertEqual(a["selected_profile_id"], b["selected_profile_id"])


class EvaluationLeaseCoordinationTests(unittest.TestCase):
    """Cron defer + lease release during evaluation (Trilha A runner coordination)."""

    def test_cron_defers_and_resumes_after_lease_release(self) -> None:
        lease_mod = _load("evaluation_lease", "evaluation_lease.py")
        owner_mod = _load("model_owner_lock", "model_owner_lock.py")

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            status_path = state / "supervisor" / "worker-status.json"
            lease_mod.acquire_evaluation_lease(state, run_id="trail-a", invocation_id="inv-1")
            deferred = lease_mod.defer_production_worker_if_evaluation_lease(
                state,
                worker_kind="direct_cycle",
                run_id="cron-1",
                status_path=status_path,
                status_schema="glitch.topstep.direct_worker_status.v2",
            )
            self.assertTrue(deferred)
            lease_mod.release_evaluation_lease(state, run_id="trail-a")
            self.assertFalse(lease_mod.evaluation_lease_active(state))
            resumed = lease_mod.defer_production_worker_if_evaluation_lease(
                state,
                worker_kind="direct_cycle",
                run_id="cron-2",
                status_path=status_path,
                status_schema="glitch.topstep.direct_worker_status.v2",
            )
            self.assertFalse(resumed)
            owner_mod.acquire_model_owner(state, owner_kind="direct_cycle", invocation_id="cron-2")
            owner_mod.release_model_owner(state, owner_kind="direct_cycle", invocation_id="cron-2")


class ParallelRunnerTests(unittest.TestCase):
    def _simple_builder(self, **kwargs: Any) -> dict:
        from ensemble_capacity_overlay import apply_capacity_gate_overlay

        fixture = kwargs.get("fixture")
        overlay = apply_capacity_gate_overlay(fixture=fixture, gate=kwargs["gate"]) if fixture else {"state": "error"}
        return {
            "schema_version": "glitch.topstep.normalized_candidate.v1",
            "profile_id": kwargs["profile"]["profile_id"],
            "invocation_id": str(uuid.uuid4()),
            "state": overlay.get("state", "error"),
            "direction": overlay.get("direction"),
            "comparability": overlay.get("comparability", "not_comparable"),
            "instrument": "MNQ",
            "latency_ms": kwargs.get("latency_ms", 0),
            "envelope_hash": kwargs["envelope"].get("snapshot_hash"),
        }

    def test_same_snapshot_hash_all_slots(self) -> None:
        run = RUN_PARALLEL.build_parallel_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        for frame in run["frame_results"]:
            sealed = frame["sealed_snapshot_hash"]
            env_hash = frame["envelope_hash"]
            self.assertTrue(sealed)
            for slot in frame["profile_slots"]:
                norm = slot["normalized"] or {}
                self.assertEqual(norm.get("envelope_hash"), env_hash)

    def test_unique_profile_and_invocation_ids(self) -> None:
        run = RUN_PARALLEL.build_parallel_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        invocation_ids: list[str] = []
        for frame in run["frame_results"]:
            profile_ids = [s["profile_id"] for s in frame["profile_slots"]]
            self.assertEqual(len(profile_ids), len(set(profile_ids)))
            for slot in frame["profile_slots"]:
                invocation_ids.append(slot["invocation_id"])
        self.assertEqual(len(invocation_ids), len(set(invocation_ids)))

    def test_hermes_home_marker_per_slot(self) -> None:
        def loader(_pid: str, _fid: str) -> dict:
            return {"state": "no_edge", "direction": "flat", "thesis": "t", "latency_ms": 1}

        results = PARALLEL.run_profiles_parallel(
            profiles=[{"profile_id": "baseline-current"}, {"profile_id": "structure"}],
            frame_id="20260820T1200Z",
            run_id="marker-test",
            envelope={"instrument": "MNQ", "snapshot_hash": "2" * 64},
            gates_by_profile={
                "baseline-current": {"comparable": True},
                "structure": {"comparable": True},
            },
            loader=loader,
            builder=self._simple_builder,
            max_parallel_slots=2,
        )
        for slot in results:
            marker = Path(slot.work_dir) / "HERMES_HOME_ISOLATED"
            self.assertTrue(marker.is_file(), slot.work_dir)
            payload = json.loads(marker.read_text(encoding="utf-8"))
            self.assertTrue(payload.get("evaluation_only"))
            self.assertEqual(payload.get("profile_id"), slot.profile_id)
        PARALLEL.cleanup_work_dirs("marker-test")

    def test_timeout_classified(self) -> None:
        def loader(_pid: str, _fid: str) -> dict:
            return {"state": "no_edge", "direction": "flat", "latency_ms": 50000}

        results = PARALLEL.run_profiles_parallel(
            profiles=[{"profile_id": "baseline-current"}],
            frame_id="f",
            run_id="timeout-test",
            envelope={"instrument": "MNQ", "snapshot_hash": "e" * 64},
            gates_by_profile={"baseline-current": {"comparable": True}},
            loader=loader,
            builder=self._simple_builder,
            per_profile_timeout_ms=100,
        )
        self.assertEqual(results[0].error, "timeout")
        self.assertEqual((results[0].raw_profile_output or {}).get("state"), "timeout")

    def test_loader_crash_classified_error(self) -> None:
        def loader(_pid: str, _fid: str) -> dict:
            raise RuntimeError("provider_down")

        results = PARALLEL.run_profiles_parallel(
            profiles=[{"profile_id": "structure"}],
            frame_id="f",
            run_id="crash-test",
            envelope={"instrument": "MNQ", "snapshot_hash": "f" * 64},
            gates_by_profile={"structure": {"comparable": True}},
            loader=loader,
            builder=self._simple_builder,
        )
        self.assertIn("provider_error", results[0].error or "")
        self.assertEqual((results[0].raw_profile_output or {}).get("state"), "error")

    def test_missing_fixture_profile_unavailable(self) -> None:
        def loader(_pid: str, _fid: str) -> dict | None:
            return None

        results = PARALLEL.run_profiles_parallel(
            profiles=[{"profile_id": "indicators"}],
            frame_id="f",
            run_id="missing-test",
            envelope={"instrument": "MNQ", "snapshot_hash": "1" * 64},
            gates_by_profile={"indicators": {"comparable": True, "missing_required": ["depth"]}},
            loader=loader,
            builder=self._simple_builder,
        )
        self.assertEqual(results[0].error, "fixture_missing")

    def test_parallel_slots_respect_max_two(self) -> None:
        active = 0
        peak = 0
        lock = __import__("threading").Lock()

        def loader(profile_id: str, frame_id: str) -> dict:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            __import__("time").sleep(0.05)
            with lock:
                active -= 1
            return {"state": "no_edge", "direction": "flat", "thesis": "x", "latency_ms": 50}

        def builder(**kwargs: Any) -> dict:
            from ensemble_capacity_overlay import apply_capacity_gate_overlay

            overlay = apply_capacity_gate_overlay(fixture=kwargs["fixture"], gate=kwargs["gate"])
            return {
                "schema_version": "glitch.topstep.normalized_candidate.v1",
                "profile_id": kwargs["profile"]["profile_id"],
                "invocation_id": "inv",
                "state": overlay["state"],
                "direction": overlay.get("direction"),
                "comparability": overlay["comparability"],
                "instrument": "MNQ",
                "latency_ms": kwargs["latency_ms"],
            }

        profiles = [{"profile_id": f"p{i}"} for i in range(4)]
        envelope = {"instrument": "MNQ", "snapshot_hash": "c" * 64}
        gates = {p["profile_id"]: {"comparable": True} for p in profiles}
        results = PARALLEL.run_profiles_parallel(
            profiles=profiles,
            frame_id="frame",
            run_id="parallel-test",
            envelope=envelope,
            gates_by_profile=gates,
            loader=loader,
            builder=builder,
            max_parallel_slots=2,
        )
        self.assertEqual(len(results), 4)
        self.assertLessEqual(peak, 2)
        work_dirs = {Path(r.work_dir) for r in results}
        self.assertEqual(len(work_dirs), 4)

    def test_cancel_remaining_slots(self) -> None:
        state = PARALLEL.ParallelRunState(max_parallel_slots=2)
        state.cancel_remaining.set()

        def loader(_pid: str, _fid: str) -> dict:
            return {"state": "no_edge", "direction": "flat", "thesis": "t"}

        def builder(**kwargs: Any) -> dict:
            return {"profile_id": kwargs["profile"]["profile_id"], "state": "no_edge"}

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            result = PARALLEL.execute_profile_slot(
                profile={"profile_id": "baseline-current"},
                frame_id="f",
                run_id="r",
                work_dir=work,
                loader=loader,
                builder=builder,
                envelope={},
                gate={"comparable": True},
                run_state=state,
                max_cost_usd=1.0,
                timeout_ms=1000,
            )
        self.assertTrue(result.cancelled)


class ParallelEnsembleIsolationTests(unittest.TestCase):
    def test_parallel_runner_does_not_import_production_workflows(self) -> None:
        import ast

        source = (SCRIPTS / "run-parallel-ensemble-evaluation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.names[0].name for node in tree.body if isinstance(node, ast.Import)
        }
        imported |= {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        forbidden = {
            "workflows",
            "intent_outbox",
            "model_owner_lock",
            "entry_delivery",
            "run_topstep_cycle",
        }
        self.assertFalse(imported & forbidden)
        RUN_PARALLEL.build_parallel_run  # module loaded
        _SEQ = _load("run_ensemble_evaluation_seq", "run-ensemble-evaluation.py")
        _SEQ.assert_runner_isolation()

    def test_parallel_run_deterministic_aggregator_across_replays(self) -> None:
        kwargs = dict(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        run_a = RUN_PARALLEL.build_parallel_run(**kwargs)
        run_b = RUN_PARALLEL.build_parallel_run(**kwargs)
        selections_a = [f["selection"]["decision_code"] for f in run_a["frame_results"]]
        selections_b = [f["selection"]["decision_code"] for f in run_b["frame_results"]]
        self.assertEqual(selections_a, selections_b)


class ParallelEnsembleIntegrationTests(unittest.TestCase):
    def test_offline_parallel_run_produces_aggregation_and_metrics(self) -> None:
        run = RUN_PARALLEL.build_parallel_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        self.assertTrue(run["evaluation_only"])
        self.assertFalse(run["production_parallelism"])
        self.assertEqual(run["max_parallel_slots"], 2)
        self.assertGreaterEqual(len(run["frame_results"]), 1)
        for frame in run["frame_results"]:
            self.assertEqual(len(frame["profile_slots"]), 6)
            self.assertIn(frame["selection"]["outcome"], {"selected", "no_selection", "classified_failure"})
            for slot in frame["profile_slots"]:
                self.assertTrue(Path(slot["work_dir"]).name)
                self.assertIn("raw_profile_output", slot)
                self.assertIn("normalized", slot)
        metrics = run["metrics"]
        self.assertEqual(metrics["schema_version"], "glitch.topstep.ensemble_metrics.v1")
        self.assertFalse(metrics["promotion_gate"])
        self.assertIn("per_profile", metrics)

    def test_isolated_work_dirs_do_not_share_state(self) -> None:
        run = RUN_PARALLEL.build_parallel_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        dirs = [slot["work_dir"] for frame in run["frame_results"] for slot in frame["profile_slots"]]
        self.assertEqual(len(dirs), len(set(dirs)))


class EnvelopeIdentitySealTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.SEAL = _load("ensemble_envelope_seal", "ensemble_envelope_seal.py")
    cls.ENV = _load("ensemble_envelope", "ensemble_envelope.py")
    cls.PREFLIGHT = _load("run_trail_a_real_preflight", "run-trail-a-real-preflight.py")
    cls.FRAME_PATH = FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json"
    cls.CONFIG = read_json(EVAL / "trail-a-real-run-config.v1.json")
    cls.MATRIX = read_json(EVAL / "capability-matrix.json")
    cls.MAPPING = read_json(EVAL / "packet_envelope_mapping.v1.json")

  def _frame(self) -> dict:
    return json.loads(self.FRAME_PATH.read_text(encoding="utf-8"))

  def _seal(self, validity_seconds: int) -> dict:
    return self.SEAL.seal_evaluation_envelope_from_frame(
      frame=self._frame(),
      source_catalog=self.MATRIX["source_catalog"],
      mapping=self.MAPPING,
      validity_seconds=validity_seconds,
      frame_path=str(self.FRAME_PATH.parent),
    )

  def test_preflight_and_execution_share_sealed_envelope(self) -> None:
    sealed = self.SEAL.seal_envelope_from_run_config(
      config=self.CONFIG,
      matrix=self.MATRIX,
      mapping=self.MAPPING,
      repo=ROOT,
    )
    check = self.PREFLIGHT.validate_pinned_envelope(
      config=self.CONFIG,
      scenarios=read_json(EVAL / "trail-a-real-scenarios.v1.json"),
      matrix=self.MATRIX,
      mapping=self.MAPPING,
    )
    self.assertTrue(check["ok"], check.get("issues"))
    self.assertEqual(check["computed"]["envelope_hash"], self.SEAL.sealed_envelope_identity(sealed)["envelope_hash"])

  def test_validity_seconds_changes_envelope_hash_not_snapshot(self) -> None:
    short = self._seal(35)
    long = self._seal(300)
    self.assertEqual(short["snapshot_hash"], long["snapshot_hash"])
    self.assertNotEqual(self.ENV.envelope_hash(short), self.ENV.envelope_hash(long))

  def test_aggregator_rejects_preflight_hash_when_candidates_are_live(self) -> None:
    snap = "8d12d081fc8885a3f89ee62f970f3f4d4fa0b429cd38bda67d9e429aee2f0542"
    preflight_hash = "5419bea167862a440dc2f9c516a88725dcd687d8e81d4bac0df4ad43307f679c"
    live_hash = "6d122b4849e61a1aaa581f98c364289886eb034db78cfe137a38010e5189b8b5"
    candidate = {
      "profile_id": "baseline-current",
      "state": "no_edge",
      "direction": "flat",
      "envelope_hash": live_hash,
    }
    result = AGG.aggregate_envelope(
      run_id="identity",
      envelope={
        "envelope_id": "env-test",
        "instrument": "MNQ",
        "snapshot_hash": snap,
        "envelope_hash": preflight_hash,
      },
      candidates=[candidate],
      rules=RULES,
    )
    self.assertEqual(result["outcome"], "classified_failure")
    self.assertEqual(result["decision_code"], "SNAPSHOT_DIVERGENCE")

  def test_aggregator_accepts_sealed_envelope_with_matching_candidates(self) -> None:
    sealed = self._seal(35)
    identity = self.SEAL.sealed_envelope_identity(sealed)
    candidates = [
      {
        "profile_id": pid,
        "state": "no_edge",
        "direction": "flat",
        "envelope_hash": identity["envelope_hash"],
      }
      for pid in ("baseline-current", "structure", "adversarial-risk")
    ]
    result = AGG.aggregate_envelope(
      run_id="sealed",
      envelope={
        "envelope_id": identity["envelope_id"],
        "instrument": identity["instrument"],
        "snapshot_hash": identity["snapshot_hash"],
        "envelope_hash": identity["envelope_hash"],
      },
      candidates=candidates,
      rules=RULES,
    )
    self.assertEqual(result["outcome"], "no_selection")
    self.assertEqual(result["decision_code"], "ENSEMBLE_UNANIMOUS_ABSTENTION")

  def test_aggregator_accepts_live_hash_post_hoc(self) -> None:
    snap = "8d12d081fc8885a3f89ee62f970f3f4d4fa0b429cd38bda67d9e429aee2f0542"
    live_hash = "6d122b4849e61a1aaa581f98c364289886eb034db78cfe137a38010e5189b8b5"
    candidates = [
      {"profile_id": pid, "state": "no_edge", "direction": "flat", "envelope_hash": live_hash}
      for pid in ("baseline-current", "structure", "adversarial-risk")
    ]
    result = AGG.aggregate_envelope(
      run_id="live",
      envelope={
        "envelope_id": "env-8d12d081fc8885a3",
        "instrument": "MNQ",
        "snapshot_hash": snap,
        "envelope_hash": live_hash,
      },
      candidates=candidates,
      rules=RULES,
    )
    self.assertEqual(result["outcome"], "no_selection")

  def test_all_profiles_share_same_envelope_hash(self) -> None:
    sealed = self._seal(35)
    eh = self.SEAL.sealed_envelope_identity(sealed)["envelope_hash"]
    hashes = {
      self.SEAL.sealed_envelope_identity(self._seal(35))["envelope_hash"],
      eh,
      eh,
    }
    self.assertEqual(len(hashes), 1)

  def test_candidate_order_invariant_for_aggregation(self) -> None:
    sealed = self._seal(35)
    identity = self.SEAL.sealed_envelope_identity(sealed)
    base = [
      {"profile_id": "structure", "state": "no_edge", "direction": "flat", "envelope_hash": identity["envelope_hash"]},
      {"profile_id": "baseline-current", "state": "no_edge", "direction": "flat", "envelope_hash": identity["envelope_hash"]},
      {"profile_id": "adversarial-risk", "state": "no_edge", "direction": "flat", "envelope_hash": identity["envelope_hash"]},
    ]
    envelope = {
      "envelope_id": identity["envelope_id"],
      "instrument": identity["instrument"],
      "snapshot_hash": identity["snapshot_hash"],
      "envelope_hash": identity["envelope_hash"],
    }
    a = AGG.aggregate_envelope(run_id="order-a", envelope=envelope, candidates=base, rules=RULES)
    b = AGG.aggregate_envelope(run_id="order-b", envelope=envelope, candidates=list(reversed(base)), rules=RULES)
    self.assertEqual(a["outcome"], b["outcome"])
    self.assertEqual(a["decision_code"], b["decision_code"])


def read_json(path: Path) -> dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
