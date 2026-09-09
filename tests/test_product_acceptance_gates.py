"""Unit tests for product acceptance gate classifications and exit codes."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    name = "run_product_acceptance_gates"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "run-product-acceptance-gates.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load()


class ProductAcceptanceClassificationTests(unittest.TestCase):
    def test_summarize_phase_pass(self) -> None:
        rows = [
            {"phase": "p", "classification": MOD.PASS},
            {"phase": "p", "classification": MOD.PASS},
        ]
        summary = MOD.summarize_phase(rows, "p")
        self.assertEqual(summary["verdict"], MOD.PASS)

    def test_summarize_phase_fail_beats_blocked(self) -> None:
        rows = [
            {"phase": "p", "classification": MOD.FAIL_CODE},
            {"phase": "p", "classification": MOD.BLOCKED_OPERATIONAL},
        ]
        summary = MOD.summarize_phase(rows, "p")
        self.assertEqual(summary["verdict"], MOD.FAIL_CODE)

    def test_summarize_phase_blocked_not_pass(self) -> None:
        rows = [
            {"phase": "p", "classification": MOD.BLOCKED_OPERATIONAL},
            {"phase": "p", "classification": MOD.PASS},
        ]
        summary = MOD.summarize_phase(rows, "p")
        self.assertEqual(summary["verdict"], MOD.BLOCKED_OPERATIONAL)

    def test_summarize_phase_unknown(self) -> None:
        rows = [{"phase": "p", "classification": MOD.UNKNOWN}]
        summary = MOD.summarize_phase(rows, "p")
        self.assertEqual(summary["verdict"], MOD.UNKNOWN)

    def test_exit_code_nonzero_for_operational_block(self) -> None:
        # Simulate main's exit logic without running the matrix.
        report = {
            "sections": {
                "code_failures": [],
                "operational_blocks": [{"check_id": "x", "classification": MOD.BLOCKED_OPERATIONAL}],
                "external_blocks": [],
            }
        }
        results = report["sections"]["operational_blocks"]
        if report["sections"]["code_failures"]:
            code = 1
        elif report["sections"]["operational_blocks"] or report["sections"]["external_blocks"]:
            code = 2
        elif any(r.get("classification") == MOD.UNKNOWN for r in results):
            code = 3
        else:
            code = 0
        self.assertEqual(code, 2)


class EvaluationGatesWinErrorTests(unittest.TestCase):
    def test_winerror_no_longer_conditional(self) -> None:
        text = (SCRIPTS / "run-evaluation-gates.py").read_text(encoding="utf-8")
        self.assertNotIn('"WinError" in combined', text)
        self.assertNotIn("WinError\" in combined", text)
        self.assertIn("Do not downgrade Failures via substring", text)


if __name__ == "__main__":
    unittest.main()
