"""REAUDIT phase 1 profile acceptance helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflows.intent_outbox import load_outbox_record, write_outbox_record


class ReauditPhase1ProfileTests(unittest.TestCase):
    def test_outbox_record_wraps_intent_with_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pkt-1.json"
            intent = {"schema_version": "glitch.intent.v3", "intent_id": "i1", "action": "EXIT"}
            write_outbox_record(path, intent, state="prepared")
            state, loaded = load_outbox_record(path)
            self.assertEqual(state, "prepared")
            self.assertEqual(loaded["intent_id"], "i1")

    def test_outbox_record_reads_legacy_intent_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(
                '{"schema_version":"glitch.intent.v3","intent_id":"legacy","action":"HOLD"}',
                encoding="utf-8",
            )
            state, loaded = load_outbox_record(path)
            self.assertEqual(state, "prepared")
            self.assertEqual(loaded["intent_id"], "legacy")


if __name__ == "__main__":
    unittest.main()
