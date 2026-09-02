"""Tests for evaluation-classification-v2.py."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "evaluation_classification_v2", SCRIPTS / "evaluation-classification-v2.py"
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EvaluationClassificationV2Tests(unittest.TestCase):
    def test_daily_capture_locked_maps_to_operationally_blocked(self) -> None:
        packet = {"execution": {"daily_capture_locked": True}}
        self.assertEqual(
            mod.classify_production_decision(packet=packet, action="NOTHING"),
            "operationally_blocked",
        )
        self.assertEqual(
            mod.classify_replay_row(
                packet=packet,
                baseline_category="no_edge",
                challenger_category="no_edge",
                comparable_pair=False,
                capacity_comparable=True,
            ),
            "operationally_blocked",
        )

    def test_no_edge_without_lock_is_valid_abstention(self) -> None:
        self.assertEqual(
            mod.classify_replay_row(
                packet={"execution": {"daily_capture_locked": False}},
                baseline_category="no_edge",
                challenger_category="no_edge",
                comparable_pair=False,
                capacity_comparable=True,
            ),
            "valid_abstention",
        )

    def test_thesis_pair_preserved_when_not_blocked(self) -> None:
        self.assertEqual(
            mod.classify_replay_row(
                packet={},
                baseline_category="thesis_quality",
                challenger_category="thesis_quality",
                comparable_pair=True,
                capacity_comparable=True,
            ),
            "comparable_thesis_pair",
        )

    def test_classify_frame_product_lock_blocks_abstention(self) -> None:
        packet = {"execution": {"daily_capture_locked": True}}
        self.assertEqual(
            mod.classify_frame_product(
                packet=packet,
                action="NOTHING",
                capacity_gate_pass=True,
                gateway_state_complete_at_decision=True,
                bar_complete=True,
            ),
            "operationally_blocked",
        )

    def test_diagnostically_evaluable_excludes_blocked(self) -> None:
        self.assertFalse(
            mod.diagnostically_evaluable(
                classification_v2="operationally_blocked",
                capture_degraded=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
