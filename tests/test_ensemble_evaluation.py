import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ENVELOPE = _load("ensemble_envelope", "ensemble_envelope.py")
CAPABILITY = _load("ensemble_capability", "ensemble_capability.py")
VALIDATE = _load("ensemble_validate", "ensemble_validate.py")
SEMANTIC = _load("ensemble_semantic", "ensemble_semantic.py")
GEOMETRY = _load("ensemble_geometry", "ensemble_geometry.py")
OVERLAY = _load("ensemble_capacity_overlay", "ensemble_capacity_overlay.py")
COMPARE = _load("ensemble_compare", "ensemble_compare.py")
RUNNER = _load("run_ensemble_evaluation", "run-ensemble-evaluation.py")


class EnsembleEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = json.loads((EVAL / "capability-matrix.json").read_text(encoding="utf-8"))
        self.registry = json.loads((EVAL / "registry.json").read_text(encoding="utf-8"))
        self.config = json.loads((EVAL / "ensemble_config.json").read_text(encoding="utf-8"))
        self.rules = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
        self.mapping = json.loads((EVAL / "packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))

    def test_runner_does_not_import_production_workflows(self) -> None:
        source = (SCRIPTS / "run-ensemble-evaluation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.names[0].name
            for node in tree.body
            if isinstance(node, ast.Import)
            for node in [node]
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
        for token in RUNNER.FORBIDDEN_IMPORT_PREFIXES:
            self.assertNotIn(f"import {token}", source)
        RUNNER.assert_runner_isolation()

    def test_control_plane_structural_and_semantic_validation(self) -> None:
        VALIDATE.validate_capability_matrix(self.matrix)
        VALIDATE.validate_registry(self.registry)
        VALIDATE.validate_ensemble_config(self.config)
        VALIDATE.validate_aggregator_rules(self.rules)
        SEMANTIC.validate_capability_matrix_semantic(self.matrix)
        SEMANTIC.validate_registry_semantic(
            self.registry,
            matrix_version=self.matrix["matrix_version"],
            config_version=self.config["config_version"],
            rules_version=self.rules["rules_version"],
        )
        SEMANTIC.validate_config_semantic(self.config, profile_count=3)
        SEMANTIC.validate_aggregator_rules_semantic(self.rules)

    def test_known_packet_builds_envelope_and_seals_snapshot_hash(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json").read_text(encoding="utf-8")
        )
        envelope = ENVELOPE.build_evaluation_envelope(
            packet=frame["packet"],
            source_catalog=self.matrix["source_catalog"],
            reference_utc=frame["captured_utc"],
            frame_id=frame["minute_id"],
            mapping=self.mapping,
        )
        sealed = envelope["snapshot_hash"]
        envelope["instrument"] = "MNQ"
        self.assertEqual(envelope["snapshot_hash"], sealed)

    def test_unknown_packet_schema_rejected(self) -> None:
        packet = {"schema_version": "glitch.direct.decision_packet.v99", "instrument": "MNQ"}
        with self.assertRaises(ValueError):
            ENVELOPE.build_evaluation_envelope(
                packet=packet,
                source_catalog=self.matrix["source_catalog"],
                reference_utc="2026-08-20T12:00:00Z",
                mapping=self.mapping,
            )

    def test_capacity_gate_preserves_direction_for_audit(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1201Z.json").read_text(encoding="utf-8")
        )
        envelope = ENVELOPE.build_evaluation_envelope(
            packet=frame["packet"],
            source_catalog=self.matrix["source_catalog"],
            reference_utc=frame["captured_utc"],
            frame_id=frame["minute_id"],
            mapping=self.mapping,
        )
        gate = CAPABILITY.capacity_gate(envelope, "structure", self.matrix)
        fixture = {"state": "held", "direction": "long", "thesis": "audit", "latency_ms": 1}
        overlay = OVERLAY.apply_capacity_gate_overlay(fixture=fixture, gate=gate)
        self.assertEqual(overlay["state"], "missing_required_evidence")
        self.assertEqual(overlay["comparability"], "not_comparable")
        self.assertEqual(overlay["profile_declared_direction"], "long")

    def test_valid_directional_candidate_geometry(self) -> None:
        codes = GEOMETRY.validate_entry_candidate_geometry(
            direction="long",
            entry=20020.0,
            entry_range=None,
            stop=20010.0,
            target=20035.0,
            reference_price=20020.0,
        )
        self.assertEqual(codes, [])

    def test_invalid_directional_candidate_geometry(self) -> None:
        codes = GEOMETRY.validate_entry_candidate_geometry(
            direction="long",
            entry=20000.0,
            entry_range=None,
            stop=20010.0,
            target=20030.0,
            reference_price=20000.0,
        )
        self.assertIn("invalid_stop_geometry", codes)

    def test_candidate_semantic_rejects_inverted_entry_range(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1201Z.json").read_text(encoding="utf-8")
        )
        envelope = ENVELOPE.build_evaluation_envelope(
            packet=frame["packet"],
            source_catalog=self.matrix["source_catalog"],
            reference_utc=frame["captured_utc"],
            frame_id=frame["minute_id"],
            mapping=self.mapping,
        )
        candidate = {
            "schema_version": "glitch.topstep.normalized_candidate.v1",
            "run_id": "r1",
            "profile_id": "baseline-current",
            "profile_version": "1.0.0",
            "invocation_id": "i1",
            "envelope_id": envelope["envelope_id"],
            "envelope_hash": ENVELOPE.envelope_hash(envelope),
            "state": "candidate",
            "comparability": "comparable",
            "instrument": "MNQ",
            "direction": "long",
            "entry_range": {"low": 20030.0, "high": 20010.0},
            "stop": 20000.0,
            "target": 20040.0,
            "started_utc": "2026-08-20T12:01:00Z",
            "finished_utc": "2026-08-20T12:01:01Z",
            "latency_ms": 1000,
            "completeness_used": {},
        }
        with self.assertRaises(ValueError):
            SEMANTIC.validate_candidate_semantic(candidate, envelope=envelope)

    def test_candidate_semantic_rejects_inconsistent_timestamps(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json").read_text(encoding="utf-8")
        )
        envelope = ENVELOPE.build_evaluation_envelope(
            packet=frame["packet"],
            source_catalog=self.matrix["source_catalog"],
            reference_utc=frame["captured_utc"],
            frame_id=frame["minute_id"],
            mapping=self.mapping,
        )
        candidate = {
            "schema_version": "glitch.topstep.normalized_candidate.v1",
            "run_id": "r1",
            "profile_id": "baseline-current",
            "profile_version": "1.0.0",
            "invocation_id": "i1",
            "envelope_id": envelope["envelope_id"],
            "envelope_hash": ENVELOPE.envelope_hash(envelope),
            "state": "no_edge",
            "comparability": "comparable",
            "instrument": "MNQ",
            "started_utc": "2026-08-20T12:01:00Z",
            "finished_utc": "2026-08-20T12:00:00Z",
            "latency_ms": 1000,
            "completeness_used": {},
        }
        with self.assertRaises(ValueError):
            SEMANTIC.validate_candidate_semantic(candidate, envelope=envelope)

    def test_candidate_semantic_rejects_instrument_divergence(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json").read_text(encoding="utf-8")
        )
        envelope = ENVELOPE.build_evaluation_envelope(
            packet=frame["packet"],
            source_catalog=self.matrix["source_catalog"],
            reference_utc=frame["captured_utc"],
            frame_id=frame["minute_id"],
            mapping=self.mapping,
        )
        candidate = {
            "schema_version": "glitch.topstep.normalized_candidate.v1",
            "run_id": "r1",
            "profile_id": "baseline-current",
            "profile_version": "1.0.0",
            "invocation_id": "i1",
            "envelope_id": envelope["envelope_id"],
            "envelope_hash": ENVELOPE.envelope_hash(envelope),
            "state": "no_edge",
            "comparability": "comparable",
            "instrument": "MES",
            "started_utc": "2026-08-20T12:00:00Z",
            "finished_utc": "2026-08-20T12:00:01Z",
            "latency_ms": 1000,
            "completeness_used": {},
        }
        with self.assertRaises(ValueError):
            SEMANTIC.validate_candidate_semantic(candidate, envelope=envelope)

    def test_offline_runner_preserves_raw_and_normalized_and_registry_manifest(self) -> None:
        run = RUNNER.build_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        baseline_manifest = next(
            row for row in run["registry_manifest"] if row["profile_id"] == "baseline-current"
        )
        registry_baseline = next(
            row for row in self.registry["profiles"] if row["profile_id"] == "baseline-current"
        )
        self.assertEqual(baseline_manifest["prompt_version"], registry_baseline["prompt_version"])
        self.assertEqual(baseline_manifest["skills"], registry_baseline["skills"])

        structure_row = None
        for frame in run["frame_results"]:
            self.assertEqual(frame["envelope"]["snapshot_hash"], frame["sealed_snapshot_hash"])
            for candidate in frame["candidates"]:
                self.assertIn("raw_profile_output", candidate)
                self.assertIn("normalized", candidate)
                VALIDATE.validate_normalized_candidate(candidate["normalized"])
                if (
                    frame["frame_id"] == "20260820T1201Z"
                    and candidate["profile_id"] == "structure"
                ):
                    structure_row = candidate
        self.assertIsNotNone(structure_row)
        normalized = structure_row["normalized"]
        self.assertEqual(normalized["state"], "missing_required_evidence")
        self.assertEqual(normalized["direction"], "long")
        self.assertEqual(normalized["comparability"], "not_comparable")

    def test_baseline_structure_comparison_categories(self) -> None:
        run = RUNNER.build_run(
            frames_dir=FIXTURES / "frozen_corpus" / "minute-frames",
            matrix_path=EVAL / "capability-matrix.json",
            registry_path=EVAL / "registry.json",
            config_path=EVAL / "ensemble_config.json",
            rules_path=EVAL / "aggregator_rules.v1.json",
            mapping_path=EVAL / "packet_envelope_mapping.v1.json",
            candidate_fixtures_dir=FIXTURES / "ensemble_candidates",
        )
        comparison_1201 = next(
            row for row in run["profile_comparisons"] if row["frame_id"] == "20260820T1201Z"
        )
        self.assertEqual(comparison_1201["challenger_category"], "missing_required_evidence")
        self.assertFalse(comparison_1201["comparable_pair"])

    def test_enriched_corpus_builder_tags_and_sanitizes(self) -> None:
        BUILD = _load("build_enriched_corpus", "build-enriched-corpus.py")
        self.assertEqual(BUILD.prac_scenario_tag("preflight-T0.json", "packet"), "preflight")
        self.assertEqual(BUILD.prac_scenario_tag("test-08-timeout-mutation.json", "post_recovery.packet"), "timeout")
        self.assertEqual(
            BUILD.prac_scenario_tag("test-02-post-audit-remediation-raw.json", "packet"),
            "reconciliation",
        )
        cleaned = BUILD.sanitize_account({"id": 1, "name": "secret", "balance": 100.0, "instrument_open_contracts": 0})
        self.assertNotIn("id", cleaned)
        self.assertNotIn("balance", cleaned)
        self.assertEqual(cleaned["name"], "PRAC-SANITIZED")

        manifest_path = FIXTURES / "frozen_corpus" / "enriched" / "manifest.json"
        self.assertTrue(manifest_path.is_file(), "run scripts/build-enriched-corpus.py to generate corpus")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(manifest["frame_count"], 1)
        entry = manifest["entries"][0]
        for key in (
            "source_file",
            "source_file_hash",
            "snapshot_hash",
            "instrument",
            "timestamp",
            "prompt_version",
            "origin",
            "scenario_tag",
            "quality",
        ):
            self.assertIn(key, entry)

    def test_corpus_join_report_exact_match_policy(self) -> None:
        JOIN = _load("audit_corpus_decision_join", "audit-corpus-decision-join.py")
        report_path = ROOT / "evaluation" / "runs" / "corpus-join-report.json"
        self.assertTrue(
            report_path.is_file(),
            "run scripts/audit-corpus-decision-join.py to generate join report",
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], JOIN.REPORT_SCHEMA)
        self.assertIn("join_policy", report)
        self.assertIn("frames", report)
        self.assertIn("receipt_audit", report)
        summary = report["summary"]
        for key in (
            "exact_cognitive_decision_match",
            "intent_only_match",
            "receipt_without_snapshot",
            "snapshot_mismatch",
            "prac_directed_execution",
            "candidate_eligible",
            "execution_only",
        ):
            self.assertIn(key, summary)
        for row in report["frames"]:
            for key in (
                "frame_id",
                "envelope_id",
                "evaluation_snapshot_hash",
                "market_snapshot_hash",
                "packet_id",
                "timestamp",
                "origin",
                "decision_join",
                "classifications",
            ):
                self.assertIn(key, row)
            classes = row["classifications"]
            self.assertIn("candidate_eligible", classes)
            self.assertIn("prac_directed_execution", classes)
            if row["decision_join"]["join_status"] == "matched":
                self.assertIsNotNone(row["decision_join"]["decision_found"])
        for receipt_row in report["receipt_audit"]["prac_intent_receipt_rows"]:
            self.assertIn("classification", receipt_row)
            self.assertFalse(receipt_row.get("thesis_quality_eligible"))

    def test_prac_decision_export_inventory_exists(self) -> None:
        inv_path = ROOT / "evaluation" / "runs" / "prac-decision-export-inventory.json"
        self.assertTrue(inv_path.is_file())
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        self.assertEqual(inv["session_id"], "PRAC-SOAK-2026-08-31")
        self.assertFalse(inv["verdict"]["contemporary_decisions_export_found"])
        self.assertEqual(inv["verdict"]["prac_packet_id_overlap_any_source"], 0)
        self.assertIn("sources", inv)
        self.assertIn("missing_exports", inv)


if __name__ == "__main__":
    unittest.main()
