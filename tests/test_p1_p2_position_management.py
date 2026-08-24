"""P1/P2: POSITION_MANAGEMENT_V1, retention prune, selective skills, debrief EV."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from position_management import (  # noqa: E402
    position_management_template,
    validate_position_management,
)
from prune_state_retention import prune_state_retention  # noqa: E402
from selection_ev import (  # noqa: E402
    fill_observability,
    selection_ev_arithmetic_audit,
)
from execution_facts_context import recent_execution_facts_for_cycle  # noqa: E402
from common import append_jsonl, write_json_atomic  # noqa: E402
import parity as PARITY  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "run_topstep_cycle_p12",
    SCRIPTS / "run-topstep-cycle.py",
)
CYCLE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CYCLE)


def _pm_text(action: str = "HOLD") -> str:
    return (
        "POSITION_MANAGEMENT_V1\n"
        "INSTRUMENT=MNQ\n"
        "POSITION_SIDE=LONG 1\n"
        "ENTRY_CURRENT_STOP_TARGET=entry=20000;current=20005;stop=19990;target=20030\n"
        "MFE_MAE_ROLLBACK=mfe=8;mae=2;rollback=1\n"
        "CURRENT_SETUP=continuation\n"
        "CONTINUATION_EVIDENCE=offers still lift\n"
        "REVERSAL_EVIDENCE=no reclaim\n"
        "NOISE_SUPPORTED_PROTECTION_LEVEL=19998\n"
        "REMAINING_OBJECTIVE=20030\n"
        "HOLD_EV=positive\n"
        "MOVE_STOP_EV=available\n"
        "MOVE_TP_EV=none\n"
        "EXIT_EV=not yet\n"
        f"SELECTION_ACTION={action}\n"
        "SELECTION_REASON=remaining EV favors action"
    )


class PositionManagementTests(unittest.TestCase):
    def test_template_and_validation(self):
        packet = {"instrument": "MNQ"}
        template = position_management_template(packet)
        self.assertIn("POSITION_MANAGEMENT_V1", template)
        self.assertIn("INSTRUMENT=MNQ", template)
        validate_position_management(_pm_text("HOLD"), packet, action="HOLD")
        with self.assertRaisesRegex(ValueError, "position_management_action_mismatch"):
            validate_position_management(_pm_text("HOLD"), packet, action="EXIT")

    def test_cycle_skills_selective(self):
        positioned = CYCLE.cycle_skills(positioned_only=True)
        self.assertIn("topstep-position-management", positioned)
        self.assertNotIn("topstep-market-scan", positioned)
        review = CYCLE.cycle_skills(trigger_review_only=True)
        self.assertNotIn("topstep-market-scan", review)
        flat = CYCLE.cycle_skills()
        self.assertIn("topstep-market-scan", flat)
        self.assertIn("topstep-position-management", flat)


class RetentionAndFactsTests(unittest.TestCase):
    def test_prune_state_retention_drops_old_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=80)
            old_stamp = cutoff - timedelta(hours=1)
            receipts = state / "receipts"
            receipts.mkdir(parents=True)
            old_receipt = receipts / "old.json"
            write_json_atomic(old_receipt, {"ok": True})
            # Force old mtime via utime
            import os

            os.utime(old_receipt, (old_stamp.timestamp(), old_stamp.timestamp()))
            frames = state / "minute-frames"
            frames.mkdir()
            old_frame = frames / "20990101T0000Z.json"
            write_json_atomic(old_frame, {"minute_id": "20990101T0000Z"})
            os.utime(old_frame, (old_stamp.timestamp(), old_stamp.timestamp()))
            append_jsonl(
                state / "execution-facts.jsonl",
                {
                    "sequence": 1,
                    "intent_id": "i1",
                    "phase": "exit_fill_observed",
                    "recorded_utc": old_stamp.isoformat().replace("+00:00", "Z"),
                },
            )
            append_jsonl(
                state / "execution-facts.jsonl",
                {
                    "sequence": 2,
                    "intent_id": "i2",
                    "phase": "entry_fill_observed",
                    "recorded_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )
            result = prune_state_retention(state)
            self.assertEqual(result["receipts_removed"], 1)
            self.assertEqual(result["minute_frames_removed"], 1)
            self.assertEqual(result["execution_facts_dropped"], 1)
            self.assertFalse(old_receipt.exists())
            kept = (state / "execution-facts.jsonl").read_text(encoding="utf-8")
            self.assertIn('"sequence":2', kept.replace(" ", ""))
            self.assertNotIn('"sequence":1', kept.replace(" ", ""))
            self.assertIn("entry_fill_observed", kept)
            self.assertNotIn("exit_fill_observed", kept)

    def test_recent_execution_facts_prefer_unmatched_exits(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            append_jsonl(
                state / "execution-facts.jsonl",
                {
                    "sequence": 1,
                    "intent_id": "open-exit",
                    "phase": "exit_fill_observed",
                    "recorded_utc": now,
                    "detail": {"realized_pnl_usd": 12.5},
                },
            )
            append_jsonl(
                state / "execution-facts.jsonl",
                {
                    "sequence": 2,
                    "intent_id": "closed",
                    "phase": "exit_fill_observed",
                    "recorded_utc": now,
                },
            )
            facts = recent_execution_facts_for_cycle(
                state,
                [{"intent_id": "closed"}],
                tail_limit=4,
            )
            ids = {row.get("intent_id") for row in facts}
            self.assertIn("open-exit", ids)


class LearningObservabilityTests(unittest.TestCase):
    def test_selection_ev_arithmetic_and_fill_observability(self):
        audit = {
            "decisive_evidence": (
                "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                "risk_points=10;reward_points=30;friction_points=1;"
                "breakeven_target_first=0.275;estimated_target_first_range=0.30-0.40;"
                "now_ev=POSITIVE;wait_price=19995;wait_ev=no;decisive_reason=edge"
            )
        }
        arithmetic = selection_ev_arithmetic_audit(audit)
        self.assertEqual(arithmetic["status"], "reconciled")
        self.assertEqual(arithmetic["arithmetic_status"], "reconciled")
        fill = fill_observability(
            {"decision_audit": audit},
            {"entry_price": 20000.25, "exit_price": 20010},
        )
        self.assertEqual(fill["status"], "observed")
        self.assertTrue(fill["entry_within_one_point"])

    def test_debrief_prompt_includes_observability(self):
        rows = [
            {
                "facts": {"outcome_id": "o1"},
                "facts_sha256": "abc",
                "entry_decision": {"action": "ENTER_LONG"},
                "related_decisions": [],
                "market_path": [],
                "selection_ev_arithmetic": {"status": "reconciled"},
                "fill_observability": {"status": "observed"},
            }
        ]
        prompt = PARITY.debrief_prompt_evidence(rows)
        self.assertEqual(prompt[0]["selection_ev_arithmetic"]["status"], "reconciled")
        self.assertEqual(prompt[0]["fill_observability"]["status"], "observed")


if __name__ == "__main__":
    unittest.main()
