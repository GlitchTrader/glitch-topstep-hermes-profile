"""Tests for expanded profiles, six-profile aggregator, shadow offline, stability, provenance."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
FIXTURES = ROOT / "tests" / "fixtures"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


AGG = _load("ensemble_aggregator", "ensemble_aggregator.py")
CAP = _load("ensemble_capability", "ensemble_capability.py")
SHADOW = _load("shadow_observe_offline", "shadow-observe-offline.py")
STABILITY = _load("report_trail_a_stability", "report-trail-a-stability.py")
PROV = _load("validate_provenance", "validate-evaluation-provenance-chain.py")
MILESTONE = _load("run_evaluation_milestone", "run-evaluation-milestone.py")
RULES = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
SIX_CASES = json.loads(
    (EVAL / "fixtures" / "aggregator_decision_cases_six_profiles.v1.json").read_text(encoding="utf-8")
)
MATRIX = json.loads((EVAL / "capability-matrix.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((EVAL / "registry.json").read_text(encoding="utf-8"))


class ExpandedProfileKitTests(unittest.TestCase):
    NEW_PROFILES = ("smart-money", "indicators", "orderflow")

    def test_profile_kits_exist_and_no_execution_authority(self) -> None:
        for pid in self.NEW_PROFILES:
            kit = json.loads((EVAL / "profiles" / f"{pid}.v1.json").read_text(encoding="utf-8"))
            self.assertFalse(kit.get("execution_authority"))
            self.assertTrue(kit.get("evaluation_enabled"))

    def test_capability_matrix_includes_new_profiles(self) -> None:
        profiles = MATRIX.get("profiles") or {}
        for pid in self.NEW_PROFILES:
            self.assertIn(pid, profiles)
            self.assertFalse(profiles[pid].get("execution_authority", True))

    def test_capacity_gate_classifies_missing_evidence(self) -> None:
        envelope = {
            "completeness": {
                "ohlc": "available",
                "quote": "available",
                "indicators": "missing_required",
                "orderflow": "missing_required",
                "structure": "missing_required",
                "session": "missing_required",
                "risk_context": "not_applicable",
            }
        }
        gate = CAP.capacity_gate(envelope, "indicators", MATRIX)
        self.assertFalse(gate["comparable"])
        self.assertIn("indicators", gate["missing_required"])

    def test_registry_has_six_enabled_profiles(self) -> None:
        enabled = [p for p in REGISTRY.get("profiles") or [] if p.get("enabled")]
        self.assertEqual(len(enabled), 6)
        self.assertEqual(REGISTRY.get("deferred_profiles"), [])
        for pid in self.NEW_PROFILES:
            row = next(p for p in enabled if p["profile_id"] == pid)
            self.assertTrue(row.get("evaluation_enabled"))
            self.assertFalse(row.get("execution_authority", True))


class AggregatorSixProfileTests(unittest.TestCase):
    def test_all_six_profile_fixtures(self) -> None:
        for case in SIX_CASES["cases"]:
            with self.subTest(case_id=case["case_id"]):
                result = AGG.aggregate_fixture_case(case, rules=RULES)
                expected = case["expected"]
                self.assertEqual(result["outcome"], expected["result"])
                self.assertEqual(result["decision_code"], expected["decision_code"])

    def test_profile_order_invariant_six_no_edge(self) -> None:
        case = next(c for c in SIX_CASES["cases"] if c["case_id"] == "SIX-NO-EDGE-01")
        profiles = list(case["inputs"]["profiles"])
        a = AGG.aggregate_fixture_case(case, rules=RULES, run_id="order-a")
        shuffled = dict(case)
        shuffled["inputs"] = dict(case["inputs"])
        shuffled["inputs"]["profiles"] = list(reversed(profiles))
        b = AGG.aggregate_fixture_case(shuffled, rules=RULES, run_id="order-b")
        self.assertEqual(a["outcome"], b["outcome"])
        self.assertEqual(a["decision_code"], b["decision_code"])

    def test_no_edge_not_in_candidate_pool(self) -> None:
        case = next(c for c in SIX_CASES["cases"] if c["case_id"] == "SIX-NO-EDGE-01")
        result = AGG.aggregate_fixture_case(case, rules=RULES)
        self.assertEqual(result["outcome"], "no_selection")
        self.assertNotIn("selected", result.get("decision_trace") or [])


class ShadowOfflineTests(unittest.TestCase):
    def test_shadow_observer_offline_no_gateway(self) -> None:
        from ensemble_envelope_seal import seal_evaluation_envelope_from_frame, sealed_envelope_identity

        mapping = json.loads((EVAL / "packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        frame_path = FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json"
        frame = json.loads(frame_path.read_text(encoding="utf-8"))
        sealed = seal_evaluation_envelope_from_frame(
            frame=frame,
            source_catalog=MATRIX["source_catalog"],
            mapping=mapping,
            validity_seconds=35,
            frame_path=str(frame_path.parent),
        )
        sealed["envelope_hash"] = sealed_envelope_identity(sealed)["envelope_hash"]
        fixtures = {}
        for pid in ("baseline-current", "structure", "adversarial-risk", "smart-money", "indicators", "orderflow"):
            p = FIXTURES / "ensemble_candidates" / pid / "20260820T1200Z.json"
            fixtures[pid] = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
        report = SHADOW.observe_envelope_offline(
            envelope=sealed,
            profile_fixtures=fixtures,
            registry=REGISTRY,
            matrix=MATRIX,
            rules=RULES,
        )
        self.assertFalse(report["shadow_live"])
        self.assertEqual(report["intents_sent"], 0)
        self.assertFalse(report["gateway_touched"])
        self.assertEqual(len(report["profile_decisions"]), 6)
        self.assertIn("aggregator_selection", report)


class TrailAStabilityTests(unittest.TestCase):
    def test_stability_report_from_trail_a_bundle(self) -> None:
        bundle = EVAL / "runs" / "trail-a-multi-envelope-2026-09-02.json"
        if not bundle.is_file():
            self.skipTest("trail-a bundle missing")
        report = STABILITY.build_trail_a_stability_report(bundle_path=bundle)
        self.assertEqual(report["envelope_count"], 3)
        self.assertFalse(report["textual_equality_required"])
        self.assertIn("baseline-current", report["per_profile"])


class ProvenanceChainTests(unittest.TestCase):
    def test_trail_a_multi_envelope_chain(self) -> None:
        bundle_path = EVAL / "runs" / "trail-a-multi-envelope-2026-09-02.json"
        if not bundle_path.is_file():
            self.skipTest("trail-a bundle missing")
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        report = PROV.validate_bundle_chain(bundle)
        self.assertEqual(report["total_rows"], 9)
        self.assertGreaterEqual(report["complete_rows"], 9)


class EvaluationMilestoneTests(unittest.TestCase):
    def test_six_profile_milestone_offline(self) -> None:
        report = MILESTONE.run_milestone(
            run_id="test-milestone-six",
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
        )
        self.assertEqual(report["profile_count"], 6)
        self.assertEqual(report["verdict"], "PASS")
        self.assertFalse(report["shadow_live"])


if __name__ == "__main__":
    unittest.main()
