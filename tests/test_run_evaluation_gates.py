"""Tests for manifest-driven evaluation gate runner."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_evaluation_gates", SCRIPTS / "run-evaluation-gates.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUNNER = _load_runner()
BLOCKED = RUNNER.BLOCKED
FAIL = RUNNER.FAIL
PASS = RUNNER.PASS
_dependency_batches = RUNNER._dependency_batches
load_manifest = RUNNER.load_manifest
run_gates = RUNNER.run_gates


class DependencyBatchTests(unittest.TestCase):
    def test_batches_respect_depends_on(self) -> None:
        gates = [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": []},
            {"id": "d", "depends_on": ["b", "c"]},
        ]
        batches = _dependency_batches(gates)
        self.assertEqual([[g["id"] for g in batch] for batch in batches], [["a", "c"], ["b"], ["d"]])


class RunnerBehaviorTests(unittest.TestCase):
    def test_live_gate_blocked_without_authorization(self) -> None:
        manifest = {
            "gates": [
                {
                    "id": "operational_stability",
                    "phase": "stability",
                    "mode": "live",
                    "live_gate": True,
                    "depends_on": [],
                    "description": "live",
                    "blocked_detail": "needs auth",
                }
            ]
        }
        report = run_gates(
            run_id="test-live-blocked",
            manifest=manifest,
            gw=None,
            authorize_live=False,
            offline_only=False,
            max_workers=1,
        )
        row = report["gates"]["operational_stability"]
        self.assertEqual(row["status"], BLOCKED)
        self.assertEqual(report["live_verdict"], BLOCKED)
        self.assertNotEqual(report["aggregate_verdict"], PASS)

    def test_blocked_never_becomes_pass(self) -> None:
        manifest = {
            "gates": [
                {
                    "id": "gateway_check",
                    "phase": "evaluation_offline",
                    "mode": "offline",
                    "requires_gateway": True,
                    "depends_on": [],
                    "description": "gw",
                }
            ]
        }
        report = run_gates(
            run_id="test-gw-missing",
            manifest=manifest,
            gw=None,
            offline_only=True,
            max_workers=1,
        )
        self.assertEqual(report["gates"]["gateway_check"]["status"], BLOCKED)
        self.assertNotEqual(report["aggregate_verdict"], PASS)
        self.assertIn(report["offline_verdict"], {BLOCKED, FAIL, RUNNER.CONDITIONAL})

    @mock.patch.object(RUNNER, "subprocess")
    def test_offline_pass_sequence(self, subprocess_mod: mock.MagicMock) -> None:
        subprocess_mod.run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        manifest = {
            "gates": [
                {
                    "id": "delivery_complete",
                    "phase": "delivery_complete",
                    "mode": "offline",
                    "depends_on": [],
                    "description": "dc",
                    "command": ["{python}", "-m", "unittest", "tests.test_coherent_evaluation_capture", "-q"],
                    "cwd": "profile",
                    "timeout_s": 30,
                }
            ]
        }
        report = run_gates(
            run_id="test-offline-pass",
            manifest=manifest,
            gw=ROOT.parent / "glitch-topstep",
            offline_only=True,
            max_workers=1,
        )
        self.assertEqual(report["gates"]["delivery_complete"]["status"], PASS)
        self.assertEqual(report["offline_verdict"], PASS)
        self.assertEqual(report["live_verdict"], "PENDING")

    def test_manifest_loads(self) -> None:
        manifest = load_manifest(ROOT / "evaluation" / "gate-manifest.v1.json")
        ids = {g["id"] for g in manifest["gates"]}
        self.assertIn("delivery_complete", ids)
        self.assertIn("process_identity", ids)
        self.assertIn("wave5_offline", ids)
        mappings = manifest.get("mappings") or {}
        self.assertIn("delivery_complete", mappings)


if __name__ == "__main__":
    unittest.main()
