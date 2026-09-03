"""Tests for single-shot shadow attempt orchestrator."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

_SPEC = importlib.util.spec_from_file_location(
    "run_shadow_live_single_attempt",
    SCRIPTS / "run-shadow-live-single-attempt.py",
)
RSA = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(RSA)


class ShadowSingleAttemptTests(unittest.TestCase):
    def test_health_blockers_degraded(self) -> None:
        blockers = RSA._health_blockers({"status": "degraded", "gateway_mode": "degraded_armed"})
        self.assertIn("gateway_status_degraded", blockers)
        self.assertIn("gateway_degraded", blockers)

    def test_health_blockers_ok(self) -> None:
        self.assertEqual(RSA._health_blockers({"status": "ok"}), [])

    def test_recovery_failed_blocks(self) -> None:
        blockers = RSA._health_blockers({"status": "ok", "recovery": {"phase": "failed"}})
        self.assertIn("recovery_failed", blockers)


if __name__ == "__main__":
    unittest.main()
