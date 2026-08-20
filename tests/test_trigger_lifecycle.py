import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "frozen_corpus"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("trigger_lifecycle", SCRIPTS / "trigger_lifecycle.py")
TL = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(TL)

from scanner_contract import MARKER  # noqa: E402


def _ledger(trigger_id: str, *, packet_id: str = "packet-1", status: str = "HELD", condition: str = "cross 20000") -> dict:
    return {
        "candidates": [
            {
                "instrument": "MNQ",
                "current_auction": "auction",
                "bullish_path": "bull",
                "bearish_path": "bear",
                "next_transition": "next",
                "triggers": [{
                    "trigger_id": trigger_id,
                    "source_packet_id": packet_id,
                    "path": "NEXT",
                    "condition": condition,
                    "expires_utc": "2026-08-20T12:05:00Z",
                    "status": status,
                }],
            },
            {
                "instrument": "MES",
                "current_auction": "auction",
                "bullish_path": "bull",
                "bearish_path": "bear",
                "next_transition": "next",
                "triggers": [{
                    "trigger_id": "trigger-mes",
                    "source_packet_id": packet_id,
                    "path": "NEXT",
                    "condition": "mes level",
                    "expires_utc": "2026-08-20T12:05:00Z",
                    "status": "HELD",
                }],
            },
        ],
        "ranking": ["MNQ", "MES"],
        "selected_instrument": "MNQ",
    }


class TriggerLifecycleTests(unittest.TestCase):
    def test_persist_restart_preserves_trigger_identity(self):
        intent = {
            "action": "NOTHING",
            "created_utc": "2026-08-20T12:00:00Z",
            "decision_audit": {"decisive_evidence": MARKER + json.dumps(_ledger("trigger-mnq"))},
        }
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            first = json.loads((state / "supervisor" / "active-comparison-triggers.json").read_text(encoding="utf-8"))
            updated = _ledger("trigger-mnq", packet_id="packet-2", status="FAILED")
            intent["decision_audit"]["decisive_evidence"] = MARKER + json.dumps(updated)
            TL.persist_comparison_triggers(state, intent, "packet-2")
            second = json.loads((state / "supervisor" / "active-comparison-triggers.json").read_text(encoding="utf-8"))
        self.assertEqual(len(first["triggers"]), 2)
        self.assertEqual({row["trigger_id"] for row in second["triggers"]}, {"trigger-mnq", "trigger-mes"})
        mnq = next(row for row in second["triggers"] if row["trigger_id"] == "trigger-mnq")
        self.assertEqual(mnq["status"], "FAILED")

    def test_nothing_with_held_trigger_schedules_rescan(self):
        intent = {
            "action": "NOTHING",
            "created_utc": "2026-08-20T12:00:00Z",
            "decision_audit": {"decisive_evidence": MARKER + json.dumps(_ledger("trigger-mnq"))},
        }
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            pending_path = TL.pending_held_rescan_path(state / "supervisor")
            self.assertTrue(pending_path.is_file())
            self.assertEqual(TL.pending_held_rescan_reason(state), "held_rescan")

    def test_ratchet_without_status_change_is_rejected(self):
        prior = {"trigger-mnq": {
            "trigger_id": "trigger-mnq",
            "status": "HELD",
            "condition": "cross 20000",
            "source_packet_id": "packet-1",
        }}
        ledger = _ledger("trigger-mnq", packet_id="packet-2", condition="cross 20010")
        with self.assertRaisesRegex(ValueError, "comparison_trigger_ratchet_detected"):
            TL.merge_comparison_triggers(prior, ledger, packet_id="packet-2")


if __name__ == "__main__":
    unittest.main()
