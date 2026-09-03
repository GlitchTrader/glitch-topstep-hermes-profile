"""Tests for phase 8 deterministic replay."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


REPLAY = _load("replay_deterministic", "replay-deterministic-evaluation.py")
AGG = _load("ensemble_aggregator", "ensemble_aggregator.py")
RULES = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
FIXTURE_CASES = json.loads(
    (EVAL / "fixtures" / "aggregator_decision_cases.v1.json").read_text(encoding="utf-8")
)


class DeterministicReplayTests(unittest.TestCase):
    def test_fixture_cases_order_invariant(self) -> None:
        for case in FIXTURE_CASES["cases"]:
            with self.subTest(case_id=case["case_id"]):
                base = AGG.aggregate_fixture_case(case, rules=RULES, run_id="replay-test")
                inputs = case["inputs"]
                envelope = {
                    "envelope_id": inputs.get("envelope_id"),
                    "instrument": inputs.get("instrument"),
                    "snapshot_hash": inputs.get("snapshot_hash"),
                    "envelope_hash": inputs.get("snapshot_hash"),
                    "contract": {"tick_size": 0.25},
                    "packet": {"market": {"last": 100.0}},
                }
                candidates = [
                    AGG._fixture_row_to_candidate(row, envelope)
                    for row in inputs.get("profiles") or []
                ]
                rng = random.Random(99)
                sig = (base["outcome"], base["decision_code"], base.get("selected_profile_id"))
                fixture_kwargs = REPLAY.fixture_aggregate_kwargs(case)
                for _ in range(5):
                    shuffled = list(candidates)
                    rng.shuffle(shuffled)
                    replay = AGG.aggregate_envelope(
                        run_id="replay-test",
                        envelope=envelope,
                        candidates=shuffled,
                        rules=RULES,
                        objections=inputs.get("objections") or [],
                        **fixture_kwargs,
                    )
                    self.assertEqual(
                        (replay["outcome"], replay["decision_code"], replay.get("selected_profile_id")),
                        sig,
                    )

    def test_classify_failure_timeout(self) -> None:
        selection = {"outcome": "classified_failure", "failure_class": "ensemble_timeout"}
        candidates = [{"state": "timeout"}]
        self.assertEqual(
            REPLAY.classify_failure(selection=selection, candidates=candidates),
            "timeout",
        )

    def test_classify_failure_thesis_error(self) -> None:
        selection = {"outcome": "no_selection", "decision_code": "DIRECTION_CONFLICT"}
        candidates = [
            {"state": "candidate", "direction": "long"},
            {"state": "candidate", "direction": "short"},
        ]
        self.assertEqual(
            REPLAY.classify_failure(selection=selection, candidates=candidates),
            "thesis_error",
        )

    def test_classify_failure_missing_evidence(self) -> None:
        selection = {"outcome": "no_selection", "decision_code": "INSUFFICIENT_ENSEMBLE_AGREEMENT"}
        candidates = [{"state": "missing_required_evidence"}]
        self.assertEqual(
            REPLAY.classify_failure(selection=selection, candidates=candidates),
            "missing_evidence",
        )

    def test_replay_milestone_bundle(self) -> None:
        bundle = EVAL / "runs" / "eval-milestone-six-profiles-2026-09-02-six-profile-ensemble.json"
        if not bundle.is_file():
            self.skipTest("milestone ensemble bundle missing")
        result = REPLAY.replay_bundle(bundle_path=bundle, rules=RULES)
        self.assertTrue(result["order_invariant"])
        self.assertIn("global_decision", result)
        self.assertIn(result["global_decision"]["outcome"], {"selected", "no_selection", "classified_failure"})

    def test_replay_trail_a_bundle(self) -> None:
        bundle = EVAL / "runs" / "trail-a-real-2026-09-02.json"
        if not bundle.is_file():
            self.skipTest("trail-a bundle missing")
        result = REPLAY.replay_bundle(bundle_path=bundle, rules=RULES)
        self.assertTrue(result["order_invariant"])
        self.assertEqual(result["failure_classification"], "data_error")


if __name__ == "__main__":
    unittest.main()
