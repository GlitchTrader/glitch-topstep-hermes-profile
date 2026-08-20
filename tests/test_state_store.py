"""Tests for indexed profile state store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from state_store import ProfileStateStore


class ProfileStateStoreTests(unittest.TestCase):
    def test_tail_decisions_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            try:
                for index in range(10):
                    store.append_decision(
                        {
                            "packet_id": f"p{index}",
                            "intent_id": f"i{index}",
                            "recorded_utc": f"2026-08-20T12:0{index % 10}:00Z",
                        },
                        jsonl_path=jsonl,
                    )
                tail = store.tail_decisions(3)
                self.assertEqual(len(tail), 3)
                self.assertEqual(tail[-1]["packet_id"], "p9")
                self.assertEqual(store.decision_by_packet("p4")["intent_id"], "i4")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
