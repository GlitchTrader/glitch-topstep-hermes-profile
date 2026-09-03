"""Tests for profile registry audit script."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_profile_registry",
        SCRIPTS / "audit-profile-registry.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit_module()


class ProfileRegistryAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = json.loads((EVAL / "registry.json").read_text(encoding="utf-8"))
        self.matrix = json.loads((EVAL / "capability-matrix.json").read_text(encoding="utf-8"))
        self.output_contract = json.loads(
            (EVAL / "evaluation_output_contract.v1.json").read_text(encoding="utf-8")
        )
        self.paired = json.loads((ROOT / "paired-contract.json").read_text(encoding="utf-8"))

    def test_production_registry_passes_audit(self) -> None:
        report = AUDIT.audit_profile_registry(
            registry=self.registry,
            matrix=self.matrix,
            profile_root=ROOT,
            output_contract=self.output_contract,
            paired_contract=self.paired,
            runs_dir=EVAL / "runs",
        )
        self.assertTrue(report["valid"], report.get("issues"))
        self.assertTrue(report["checks"]["promotion_status_blocked"])
        self.assertTrue(
            report["checks"]["execution_mode_offline_parallel_evaluation"]
            or report["checks"]["execution_mode_offline_sequential"]
        )
        self.assertGreater(len(report["checks"]["enabled_profiles"]), 0)
        self.assertGreater(report["ensemble_compatibility"]["artifact_count"], 0)

    def test_missing_skill_fails(self) -> None:
        broken = json.loads(json.dumps(self.registry))
        broken["profiles"][0]["skills"].append("topstep-nonexistent-skill")
        report = AUDIT.audit_profile_registry(
            registry=broken,
            matrix=self.matrix,
            profile_root=ROOT,
            output_contract=self.output_contract,
            paired_contract=self.paired,
        )
        self.assertFalse(report["valid"])
        self.assertTrue(any("skill_missing_on_disk" in issue for issue in report["issues"]))

    def test_unblocked_promotion_fails(self) -> None:
        broken = json.loads(json.dumps(self.registry))
        broken["promotion_status"] = "armed"
        report = AUDIT.audit_profile_registry(
            registry=broken,
            matrix=self.matrix,
            profile_root=ROOT,
            output_contract=self.output_contract,
            paired_contract=self.paired,
        )
        self.assertFalse(report["valid"])
        self.assertFalse(report["checks"]["promotion_status_blocked"])

    def test_script_writes_audit_report(self) -> None:
        output = EVAL / "runs" / "profile-registry-audit-test.json"
        if output.is_file():
            output.unlink()
        completed = __import__("subprocess").run(
            [sys.executable, str(SCRIPTS / "audit-profile-registry.py"), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(output.is_file())
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["valid"])
        output.unlink()


if __name__ == "__main__":
    unittest.main()
