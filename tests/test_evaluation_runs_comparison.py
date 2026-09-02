"""Tests for multi-run evaluation comparison reporting."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "evaluation_runs"
sys.path.insert(0, str(SCRIPTS))

from evaluation_cost import audit_evaluation_costs
from report_evaluation_metrics import _load_artifacts


def _load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


COMPARISON = _load_module("report-evaluation-runs-comparison.py", "report_evaluation_runs_comparison")


class EvaluationRunsComparisonTests(unittest.TestCase):
    def test_build_comparison_from_fixture_bundles(self) -> None:
        paths = [FIXTURES / "bundle-run-a.json", FIXTURES / "bundle-run-b.json"]
        report = COMPARISON.build_comparison_report(paths)
        self.assertEqual(report["schema_version"], "glitch.topstep.evaluation_runs_comparison.v1")
        self.assertEqual(report["bundle_count"], 2)
        self.assertEqual(len(report["runs"]), 2)
        agg = report["aggregated"]
        self.assertEqual(agg["invocation_count"], 4)
        self.assertEqual(agg["thesis_quality"]["comparable_pair_count"], 1)
        self.assertEqual(agg["cognitive_divergence"]["direction_delta_count"], 1)
        self.assertEqual(agg["missing_required_evidence"]["missing_required_evidence_count"], 1)
        self.assertFalse(agg["cost_latency"]["audit_gate_passed"])

    def test_run_sections_include_required_keys(self) -> None:
        bundle_path = FIXTURES / "bundle-run-a.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        artifacts = COMPARISON._filter_profiles(_load_artifacts([bundle_path]), ("baseline-current", "structure"))
        sections = COMPARISON.build_run_sections(bundle=bundle, artifacts=artifacts)
        for key in (
            "contract_validity",
            "missing_required_evidence",
            "not_comparable",
            "thesis_quality",
            "cognitive_divergence",
            "intra_profile_stability",
            "cost_latency",
            "evidence_completeness",
        ):
            self.assertIn(key, sections)
        self.assertIn("placeholder", sections["intra_profile_stability"])
        self.assertTrue(sections["cost_latency"]["audit_gate_passed"])

    def test_rates_include_denominator_objects(self) -> None:
        paths = [FIXTURES / "bundle-run-a.json", FIXTURES / "bundle-run-b.json"]
        report = COMPARISON.build_comparison_report(paths)
        agg = report["aggregated"]
        invalid_rate = agg["contract_validity"]["invalid_rate"]
        self.assertEqual(invalid_rate["numerator"], 0)
        self.assertEqual(invalid_rate["denominator"], 4)
        comparable_pair_rate = agg["thesis_quality"]["comparable_pair_rate"]
        self.assertEqual(comparable_pair_rate["numerator"], 1)
        self.assertEqual(comparable_pair_rate["denominator"], 2)
        direction_delta_rate = agg["cognitive_divergence"]["direction_delta_rate"]
        self.assertEqual(direction_delta_rate["numerator"], 1)
        self.assertEqual(direction_delta_rate["denominator"], 1)
        unknown_pricing = agg["cost_latency"]["unknown_pricing_rate"]
        self.assertEqual(unknown_pricing["numerator"], 1)
        self.assertEqual(unknown_pricing["denominator"], 4)
        baseline_profile = agg["evidence_completeness"]["by_profile"]["baseline-current"]
        self.assertIn("comparable_rate", baseline_profile)
        self.assertEqual(baseline_profile["comparable_rate"]["denominator"], 2)

    def test_default_bundle_glob_includes_existing_runs(self) -> None:
        paths = COMPARISON._expand_paths(
            [
                "evaluation/runs/scenario-live-2026-09-01-r7-contract.json",
                "evaluation/runs/scenario-live-2026-09-01-r8-contract.json",
                "evaluation/runs/scenario-live-2026-09-01-r9-v2.json",
            ],
            repo=ROOT,
        )
        run_ids = {path.name for path in paths}
        self.assertIn("scenario-live-2026-09-01-r7-contract.json", run_ids)
        self.assertIn("scenario-live-2026-09-01-r8-contract.json", run_ids)
        if (ROOT / "evaluation/runs/scenario-live-2026-09-01-r9-v2.json").is_file():
            self.assertIn("scenario-live-2026-09-01-r9-v2.json", run_ids)


class EvaluationCostAuditTests(unittest.TestCase):
    def test_audit_flags_unknown_pricing(self) -> None:
        artifacts = _load_artifacts([FIXTURES / "bundle-run-b.json"])
        report = audit_evaluation_costs(artifacts)
        self.assertGreater(report["unknown_pricing_count"], 0)
        self.assertFalse(report["audit_gate_passed"])
        self.assertGreater(report["estimated_vs_provider"]["estimated_total_usd"], 0.0)

    def test_audit_accumulates_session_cost(self) -> None:
        artifacts = _load_artifacts([FIXTURES / "bundle-run-a.json"])
        report = audit_evaluation_costs(artifacts)
        self.assertIn("sess-a", report["sessions"])
        self.assertAlmostEqual(report["sessions"]["sess-a"]["accumulated_cost_usd"], 0.0021, places=4)
        self.assertTrue(report["audit_gate_passed"])


if __name__ == "__main__":
    unittest.main()
