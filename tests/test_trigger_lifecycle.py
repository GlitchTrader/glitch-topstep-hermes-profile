import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("trigger_lifecycle", SCRIPTS / "trigger_lifecycle.py")
TL = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(TL)

from scanner_contract import serialize_comparison_line  # noqa: E402


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
        "selection_reason": "MNQ retains best edge",
    }


def _intent_from_ledger(ledger: dict, *, packet_id: str = "packet-1", action: str = "NOTHING") -> dict:
    return {
        "action": action,
        "created_utc": "2026-08-20T12:00:00Z",
        "packet_id": packet_id,
        "expires_utc": "2026-08-20T12:05:00Z",
        "decision_audit": {
            "decisive_evidence": serialize_comparison_line(
                ledger,
                packet_id=packet_id,
                expires_utc="2026-08-20T12:05:00Z",
                action=action,
            )
        },
    }


def _flat_packet(minute: int = 0) -> dict:
    return {
        "packet_id": "packet-live",
        "created_utc": f"2026-08-20T12:{minute:02d}:00Z",
    }


class TriggerLifecycleTests(unittest.TestCase):
    def test_persist_restart_preserves_trigger_identity(self):
        intent = _intent_from_ledger(_ledger("trigger-mnq"))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            first = json.loads((state / "supervisor" / "active-comparison-triggers.json").read_text(encoding="utf-8"))
            updated = _ledger("trigger-mnq", packet_id="packet-2", status="FAILED")
            intent = _intent_from_ledger(updated, packet_id="packet-2")
            TL.persist_comparison_triggers(state, intent, "packet-2")
            second = json.loads((state / "supervisor" / "active-comparison-triggers.json").read_text(encoding="utf-8"))
        self.assertEqual(len(first["triggers"]), 2)
        self.assertEqual({row["trigger_id"] for row in second["triggers"]}, {"trigger-mnq", "trigger-mes"})
        mnq = next(row for row in second["triggers"] if row["trigger_id"] == "trigger-mnq")
        self.assertEqual(mnq["status"], "FAILED")

    def test_nothing_with_held_trigger_schedules_rescan(self):
        ledger = _ledger("trigger-mnq")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2099-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger)
        intent["expires_utc"] = "2099-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            pending_path = TL.pending_held_rescan_path(state / "supervisor")
            self.assertTrue(pending_path.is_file())
            self.assertIsNone(TL.pending_held_rescan_reason(state, _flat_packet(0)))
            self.assertEqual(
                TL.pending_held_rescan_reason(state, _flat_packet(5)),
                "held_rescan",
            )

    def test_held_rescan_waits_for_flat_cadence(self):
        ledger = _ledger("trigger-mnq")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2099-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger)
        intent["expires_utc"] = "2099-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            pending_path = TL.pending_held_rescan_path(state / "supervisor")
            self.assertTrue(pending_path.is_file())
            self.assertIsNone(TL.pending_held_rescan_reason(state, _flat_packet(3)))
            self.assertEqual(
                TL.pending_held_rescan_reason(state, _flat_packet(5)),
                "held_rescan",
            )

    def test_new_ledger_supersedes_prior_instrument_held(self):
        ledger = _ledger("trigger-mnq")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2099-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger, packet_id="packet-1")
        intent["expires_utc"] = "2099-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            next_ledger = _ledger("trigger-mnq-next", packet_id="packet-2")
            for row in next_ledger["candidates"]:
                for trigger in row["triggers"]:
                    trigger["expires_utc"] = "2099-01-01T12:10:00Z"
            next_intent = _intent_from_ledger(next_ledger, packet_id="packet-2")
            next_intent["expires_utc"] = "2099-01-01T12:10:00Z"
            TL.persist_comparison_triggers(state, next_intent, "packet-2")
            document = json.loads(
                (state / "supervisor" / "active-comparison-triggers.json").read_text(
                    encoding="utf-8"
                )
            )
        prior = next(
            row for row in document["triggers"] if row["trigger_id"] == "trigger-mnq"
        )
        self.assertEqual(prior["status"], "EXPIRED")
        current = next(
            row
            for row in document["triggers"]
            if row["trigger_id"] == "trigger-mnq-next"
        )
        self.assertEqual(current["status"], "HELD")

    def test_expired_held_does_not_schedule_rescan(self):
        ledger = _ledger("trigger-mnq", status="HELD", condition="cross 20000")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2000-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger)
        intent["expires_utc"] = "2000-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            pending_path = TL.pending_held_rescan_path(state / "supervisor")
            self.assertFalse(pending_path.is_file())
            self.assertIsNone(
                TL.pending_held_rescan_reason(state, _flat_packet(0))
            )

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

    def test_evaluate_comparison_trigger_fires_on_cross(self):
        ledger = _ledger("trigger-mnq", condition="cross 20000")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2099-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger)
        intent["expires_utc"] = "2099-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            path = TL.comparison_trigger_path(state / "supervisor")
            document = json.loads(path.read_text(encoding="utf-8"))
            document["eval_snapshot"] = {"price": 19990.0}
            path.write_text(json.dumps(document), encoding="utf-8")
            packet = {
                "packet_id": "packet-live",
                "market": {"last": 20010.0},
            }
            fired = TL.evaluate_comparison_triggers(state, packet)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["trigger_id"], "trigger-mnq")
        detail = TL.comparison_wake_detail(fired[0])
        self.assertEqual(detail["wake_reason"], "COMPARISON_TRIGGER:MNQ:trigger-mnq")

    def test_reconcile_persists_expired_held_to_disk(self):
        ledger = _ledger("trigger-mnq")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2000-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger)
        intent["expires_utc"] = "2000-01-01T12:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            TL.pending_held_rescan_reason(state, _flat_packet(0))
            document = json.loads(
                (state / "supervisor" / "active-comparison-triggers.json").read_text(
                    encoding="utf-8"
                )
            )
        statuses = {row["trigger_id"]: row["status"] for row in document["triggers"]}
        self.assertEqual(statuses["trigger-mnq"], "EXPIRED")

    def test_omitted_instrument_is_expired_on_new_ledger(self):
        ledger = _ledger("trigger-mnq")
        for row in ledger["candidates"]:
            for trigger in row["triggers"]:
                trigger["expires_utc"] = "2099-01-01T12:05:00Z"
        intent = _intent_from_ledger(ledger, packet_id="packet-1")
        intent["expires_utc"] = "2099-01-01T12:05:00Z"
        partial = _ledger("trigger-mnq-next", packet_id="packet-2")
        partial["candidates"] = [partial["candidates"][0]]
        partial["ranking"] = ["MNQ"]
        next_intent = _intent_from_ledger(partial, packet_id="packet-2")
        next_intent["expires_utc"] = "2099-01-01T12:10:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            TL.persist_comparison_triggers(state, intent, "packet-1")
            TL.persist_comparison_triggers(state, next_intent, "packet-2")
            document = json.loads(
                (state / "supervisor" / "active-comparison-triggers.json").read_text(
                    encoding="utf-8"
                )
            )
        mes = next(row for row in document["triggers"] if row["trigger_id"] == "trigger-mes")
        self.assertEqual(mes["status"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
