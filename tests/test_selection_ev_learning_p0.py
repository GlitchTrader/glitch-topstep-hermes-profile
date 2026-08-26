"""SELECTION_EV contract and learning P0 gates (NT parity)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from selection_ev import validate_selection_ev  # noqa: E402
from scanner_contract import comparison_line_template, validate_comparison_ledger  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "run_topstep_learning_nt",
    SCRIPTS / "run-topstep-learning.py",
)
LEARNING = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(LEARNING)


POSITIVE_ROBUST_LONG = (
    "direction=LONG;entry=20000;stop=19990;target=20030;risk_points=10;reward_points=30;"
    "friction_points=1;breakeven_target_first=0.275;estimated_target_first_range=0.35-0.45;"
    "now_ev=POSITIVE_ROBUST;wait_price=19995;wait_ev=no improvement;decisive_reason=edge"
)
NEGATIVE_LONG = (
    "direction=LONG;entry=20000;stop=19990;target=20030;risk_points=10;reward_points=30;"
    "friction_points=1;breakeven_target_first=0.275;estimated_target_first_range=0.20-0.25;"
    "now_ev=NEGATIVE;wait_price=19995;wait_ev=no improvement;decisive_reason=no edge"
)


class SelectionEvTests(unittest.TestCase):
    def test_entry_requires_positive(self):
        validate_selection_ev(POSITIVE_ROBUST_LONG, "ENTER_LONG")
        with self.assertRaisesRegex(ValueError, "selection_ev_entry_not_positive"):
            validate_selection_ev(NEGATIVE_LONG, "ENTER_LONG")

    def test_nothing_forbids_robust_positive(self):
        validate_selection_ev(NEGATIVE_LONG, "NOTHING")
        with self.assertRaisesRegex(ValueError, "selection_ev_nothing_positive"):
            validate_selection_ev(POSITIVE_ROBUST_LONG, "NOTHING")

    def test_nothing_allows_positive_thin(self):
        thin = (
            "direction=LONG;entry=20000;stop=19990;target=20030;risk_points=10;reward_points=30;"
            "friction_points=1;breakeven_target_first=0.275;estimated_target_first_range=0.28-0.32;"
            "now_ev=POSITIVE_THIN;wait_price=19995;wait_ev=no improvement;decisive_reason=thin edge"
        )
        validate_selection_ev(thin, "NOTHING")

    def test_rejects_legacy_positive_verdict(self):
        legacy = (
            "direction=LONG;entry=20000;stop=19990;target=20030;risk_points=10;reward_points=30;"
            "friction_points=1;breakeven_target_first=0.275;estimated_target_first_range=0.35-0.45;"
            "now_ev=POSITIVE;wait_price=19995;wait_ev=no improvement;decisive_reason=edge"
        )
        with self.assertRaisesRegex(ValueError, "selection_ev_verdict_legacy_positive"):
            validate_selection_ev(legacy, "ENTER_LONG")

    def test_flat_direction_infers_long_from_geometry(self):
        flat = (
            "direction=FLAT;entry=20000;stop=19990;target=20030;risk_points=10;reward_points=30;"
            "friction_points=1;breakeven_target_first=0.275;estimated_target_first_range=0.20-0.25;"
            "now_ev=NEGATIVE;wait_price=19995;wait_ev=no improvement;decisive_reason=no edge"
        )
        validate_selection_ev(flat, "NOTHING")

    def test_rewrites_misstated_breakeven_fraction(self):
        wrong_be = (
            "direction=SHORT;entry=29169;stop=29185;target=29159;risk_points=16;reward_points=10;"
            "friction_points=0.5;breakeven_target_first=0.56;estimated_target_first_range=0.35-0.45;"
            "now_ev=NEGATIVE;wait_price=29167.5;wait_ev=no improvement;decisive_reason=no edge"
        )
        validate_selection_ev(wrong_be, "NOTHING")

    def test_flat_without_geometry_still_invalid(self):
        flat = (
            "direction=FLAT;entry=NA;stop=NA;target=NA;risk_points=NA;reward_points=NA;"
            "friction_points=NA;breakeven_target_first=NA;estimated_target_first_range=NA;"
            "now_ev=NEGATIVE;wait_price=19995;wait_ev=POSITIVE;decisive_reason=no edge"
        )
        with self.assertRaisesRegex(ValueError, "selection_ev_direction_invalid|selection_ev_numeric_invalid"):
            validate_selection_ev(flat, "NOTHING")

    def test_template_includes_selection_ev(self):
        packet = {
            "instrument": "MNQ",
            "market_universe": {
                "candidates": [
                    {"instrument": "MNQ"},
                    {"instrument": "MES"},
                ]
            },
        }
        self.assertIn("SELECTION_EV=", comparison_line_template(packet))


class LearningP0Tests(unittest.TestCase):
    def test_quarantines_unreconciled_eligible_outcome(self):
        row = {
            "learning_eligible": True,
            "protection_status": "pending",
            "fills": [],
        }
        self.assertFalse(LEARNING.outcome_is_reconciled_for_learning(row))
        row["protection_status"] = "confirmed"
        row["fills"] = [{"qty": 1}]
        self.assertTrue(LEARNING.outcome_is_reconciled_for_learning(row))

    def test_promotion_gate_requires_cross_session_general_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = Path(tmp)
            episodes = [
                {
                    "episode_id": "ep-1",
                    "decision_utc": "2026-08-17T15:00:00Z",
                    "evidence_context": {"session_date_et": "2026-08-17"},
                },
                {
                    "episode_id": "ep-2",
                    "decision_utc": "2026-08-18T15:00:00Z",
                    "evidence_context": {"session_date_et": "2026-08-18"},
                },
            ]
            (supervisor / "decision-episodes.jsonl").write_text(
                "\n".join(
                    __import__("json").dumps(row) for row in episodes
                )
                + "\n",
                encoding="utf-8",
            )
            (supervisor / "trade-episodes.jsonl").write_text("", encoding="utf-8")
            self.assertTrue(
                LEARNING.promotion_gate_allows_proposal(
                    supervisor,
                    ["ep-1", "ep-2"],
                    expected_old_text="Treat incomplete evidence as uncertainty.",
                    replacement_text="Treat incomplete evidence as an uncertainty cost.",
                    evaluation_metric="Later target-before-stop calibration",
                    rollback_condition="Rollback if calibration degrades",
                )
            )
            self.assertFalse(
                LEARNING.promotion_gate_allows_proposal(
                    supervisor,
                    ["ep-1", "ep-2"],
                    expected_old_text="Treat incomplete evidence as uncertainty.",
                    replacement_text="Always enter MNQ long at 09:30.",
                    evaluation_metric="Later target-before-stop calibration",
                    rollback_condition="Rollback if calibration degrades",
                )
            )


if __name__ == "__main__":
    unittest.main()
