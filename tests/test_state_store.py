"""Tests for indexed profile state store."""

from __future__ import annotations

import json
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

    def test_tail_decisions_stays_current_after_jsonl_grows_post_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            jsonl.write_text(
                json.dumps(
                    {
                        "packet_id": "p0",
                        "intent_id": "i0",
                        "recorded_utc": "2026-08-20T12:00:00Z",
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            store = ProfileStateStore(state)
            try:
                store.bootstrap_decisions(jsonl)
                self.assertEqual(store.tail_decisions(10)[-1]["packet_id"], "p0")

                from common import append_jsonl

                append_jsonl(
                    jsonl,
                    {
                        "packet_id": "p1",
                        "intent_id": "i1",
                        "recorded_utc": "2026-08-20T12:01:00Z",
                    },
                )

                tail = store.tail_decisions(10)
                self.assertEqual(
                    [row["packet_id"] for row in tail],
                    ["p0", "p1"],
                    "cycle must index new decisions, not freeze after bootstrap",
                )
            finally:
                store.close()

    def test_export_queue_drains_after_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            try:
                store.append_decision(
                    {
                        "packet_id": "p-export",
                        "intent_id": "i-export",
                        "recorded_utc": "2026-08-21T12:00:00Z",
                    },
                    jsonl_path=jsonl,
                )
                self.assertEqual(store.export_backlog_count(jsonl), 0)
                self.assertTrue(jsonl.is_file())
                lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertIn("p-export", lines[0])
            finally:
                store.close()

    def test_export_queue_survives_crash_before_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            try:
                payload = json.dumps(
                    {
                        "packet_id": "p-crash",
                        "intent_id": "i-crash",
                        "recorded_utc": "2026-08-21T12:01:00Z",
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                with store.db:
                    store._insert_decision(json.loads(payload))
                    store.db.execute(
                        """
                        INSERT INTO jsonl_export_queue(target, payload_json, created_utc)
                        VALUES (?, ?, ?)
                        """,
                        (str(jsonl), payload, "2026-08-21T12:01:00Z"),
                    )
                self.assertEqual(store.export_backlog_count(jsonl), 1)
                self.assertFalse(jsonl.is_file())
                exported = store.export_pending_jsonl(jsonl)
                self.assertEqual(exported, 1)
                self.assertTrue(jsonl.is_file())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
