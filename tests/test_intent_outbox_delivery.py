"""Tests for intent outbox delivery state transitions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workflows.intent_outbox import (  # noqa: E402
    finalize_outbox_after_delivery,
    load_outbox_record,
    write_outbox_record,
)


class IntentOutboxDeliveryTests(unittest.TestCase):
    def test_transport_uncertain_keeps_delivery_unknown_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outbox.json"
            intent = {"intent_id": "i1", "action": "ENTER_LONG"}
            write_outbox_record(path, intent, state="prepared")
            state = finalize_outbox_after_delivery(
                path,
                intent,
                "transport_uncertain",
            )
            self.assertEqual(state, "delivery_unknown")
            loaded_state, _ = load_outbox_record(path)
            self.assertEqual(loaded_state, "delivery_unknown")

    def test_successful_transitions_to_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outbox.json"
            intent = {"intent_id": "i2", "action": "NOTHING"}
            write_outbox_record(path, intent, state="prepared")
            state = finalize_outbox_after_delivery(path, intent, "successful")
            self.assertEqual(state, "registered")
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["state"], "registered")


if __name__ == "__main__":
    unittest.main()
