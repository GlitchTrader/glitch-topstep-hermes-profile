"""Tests for capability matrix audit script."""

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
        "audit_capability_matrix",
        SCRIPTS / "audit-capability-matrix.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit_module()


class CapabilityMatrixAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = json.loads((EVAL / "capability-matrix.json").read_text(encoding="utf-8"))
        self.registry = json.loads((EVAL / "registry.json").read_text(encoding="utf-8"))

    def test_production_matrix_passes_audit(self) -> None:
        report = AUDIT.audit_capability_matrix(
            matrix=self.matrix,
            registry=self.registry,
            profile_root=ROOT,
        )
        self.assertTrue(report["valid"], report.get("issues"))
        self.assertTrue(report["profile_flags"])
        self.assertFalse(report["checks"]["comparability_covers_required_sources"])

    def test_unknown_registry_skill_fails(self) -> None:
        broken_registry = json.loads(json.dumps(self.registry))
        broken_registry["profiles"][0]["skills"].append("topstep-nonexistent-skill")
        report = AUDIT.audit_capability_matrix(
            matrix=self.matrix,
            registry=broken_registry,
            profile_root=ROOT,
        )
        self.assertFalse(report["valid"])
        self.assertTrue(any("registry_skill_missing" in issue for issue in report["issues"]))

    def test_required_optional_overlap_fails(self) -> None:
        broken = json.loads(json.dumps(self.matrix))
        profile = broken["profiles"]["baseline-current"]
        profile["optional_sources"] = list(profile["required_sources"])
        report = AUDIT.audit_capability_matrix(
            matrix=broken,
            registry=self.registry,
            profile_root=ROOT,
        )
        self.assertFalse(report["valid"])
        self.assertTrue(any("required_optional_overlap" in issue for issue in report["issues"]))

    def test_invalid_packet_path_syntax_fails(self) -> None:
        broken = json.loads(json.dumps(self.matrix))
        broken["source_catalog"]["ohlc"]["packet_paths"].append("not-a-valid-path!")
        report = AUDIT.audit_capability_matrix(
            matrix=broken,
            registry=self.registry,
            profile_root=ROOT,
        )
        self.assertFalse(report["valid"])
        self.assertTrue(any("packet_path_syntax_invalid" in issue for issue in report["issues"]))

    def test_script_writes_audit_report(self) -> None:
        output = EVAL / "runs" / "capability-matrix-audit-test.json"
        if output.is_file():
            output.unlink()
        completed = __import__("subprocess").run(
            [
                sys.executable,
                str(SCRIPTS / "audit-capability-matrix.py"),
                "--output",
                str(output),
            ],
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
