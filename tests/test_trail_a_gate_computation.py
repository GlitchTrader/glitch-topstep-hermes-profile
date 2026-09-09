"""Trail A gate computation — no hardcoded PASS literals."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_trail():
    path = SCRIPTS / "run-trail-a-acceptance.py"
    spec = importlib.util.spec_from_file_location("run_trail_a_acceptance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_trail_a_acceptance"] = module
    spec.loader.exec_module(module)
    return module


trail = _load_trail()


class TrailAGateComputationTests(unittest.TestCase):
    def test_runner_touches_forbidden_paths_detects_mtime_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            target = prod / "state" / "outbox" / "intent.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}", encoding="utf-8")
            before = {str(target): target.stat().st_mtime - 10}
            after = {str(target): target.stat().st_mtime}
            with mock.patch(
                "evaluation_owner.production_profile_root", return_value=prod
            ), mock.patch(
                "evaluation_owner.is_forbidden_production_path", return_value=True
            ):
                result = trail.audit_production_writes(
                    before=before, after=after, runner_hermes_homes=[str(prod / "eval")]
                )
            self.assertTrue(result["verification_executed"])
            self.assertTrue(result["runner_touches_forbidden_paths"])

    def test_runner_touches_forbidden_paths_clean_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            fp = {str(prod / "state" / "outbox" / "x"): 1.0}
            with mock.patch(
                "evaluation_owner.production_profile_root", return_value=prod
            ), mock.patch(
                "evaluation_owner.is_forbidden_production_path", return_value=True
            ):
                result = trail.audit_production_writes(
                    before=fp,
                    after=fp,
                    runner_hermes_homes=[str(prod / "evaluation" / "state")],
                )
            self.assertTrue(result["verification_executed"])
            self.assertFalse(result["runner_touches_forbidden_paths"])

    def test_failures_classified_pass_when_all_labeled(self) -> None:
        parallel = {
            "frame_results": [
                {
                    "frame_id": "f1",
                    "selection": {"outcome": "selected"},
                    "profile_slots": [
                        {"profile_id": "a", "error": True, "failure_class": "timeout"},
                        {"profile_id": "b", "cancelled": True, "failure_class": "budget"},
                    ],
                }
            ]
        }
        audit = trail.classify_parallel_failures(parallel)
        self.assertTrue(audit["verification_executed"])
        self.assertTrue(audit["failures_classified"])

    def test_failures_classified_fail_when_unlabeled(self) -> None:
        parallel = {
            "frame_results": [
                {
                    "frame_id": "f1",
                    "selection": {"outcome": "selected"},
                    "profile_slots": [{"profile_id": "a", "error": True}],
                }
            ]
        }
        audit = trail.classify_parallel_failures(parallel)
        self.assertTrue(audit["verification_executed"])
        self.assertFalse(audit["failures_classified"])

    def test_failures_classified_unknown_when_not_executed(self) -> None:
        audit = trail.classify_parallel_failures({"frame_results": None})
        self.assertFalse(audit["verification_executed"])
        self.assertIsNone(audit["failures_classified"])
        self.assertEqual(audit["status"], "unknown")

    def test_source_has_no_hardcoded_pass_literals(self) -> None:
        source = (SCRIPTS / "run-trail-a-acceptance.py").read_text(encoding="utf-8")
        self.assertNotIn('"runner_touches_forbidden_paths": False', source)
        self.assertNotIn('"failures_classified": True', source)


if __name__ == "__main__":
    unittest.main()
