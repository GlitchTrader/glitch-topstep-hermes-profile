"""REAUDIT phase 2 profile — incremental sync + journal helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import journal_metrics, rotate_jsonl
from state_store import ProfileStateStore


class ReauditPhase2ProfileTests(unittest.TestCase):
    def test_sync_uses_byte_offset_without_rescanning_whole_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            jsonl.write_text(
                json.dumps({"packet_id": "p0", "recorded_utc": "2026-08-21T12:00:00Z"})
                + "\n",
                encoding="utf-8",
            )
            store = ProfileStateStore(state)
            try:
                store.bootstrap_decisions(jsonl)
                offset = store.db.execute(
                    "SELECT value FROM sync_meta WHERE key = 'decisions_jsonl_offset'"
                ).fetchone()[0]
                self.assertTrue(int(offset) > 0)

                from common import append_jsonl

                append_jsonl(
                    jsonl,
                    {"packet_id": "p1", "recorded_utc": "2026-08-21T12:01:00Z"},
                )
                store.sync_decisions_from_jsonl(jsonl)
                packets = [row["packet_id"] for row in store.tail_decisions(10)]
                self.assertEqual(packets, ["p0", "p1"])
            finally:
                store.close()

    def test_rotate_jsonl_default_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.jsonl"
            path.write_text('{"x":1}\n', encoding="utf-8")
            self.assertIsNone(rotate_jsonl(path, max_bytes=1, enabled=False))
            self.assertTrue(path.is_file())

    def test_journal_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.jsonl"
            path.write_text('{"a":1}\n\n{"b":2}\n', encoding="utf-8")
            metrics = journal_metrics(path)
            self.assertEqual(metrics["lines"], 2)
            self.assertGreater(metrics["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
