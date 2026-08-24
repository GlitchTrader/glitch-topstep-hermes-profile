"""Tests for audit wave A/B profile remediation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import append_jsonl, jsonl_contains_sequence  # noqa: E402
from process_supervisor import run_supervised  # noqa: E402
from prune_state_retention import prune_state_retention  # noqa: E402
from state_store import ProfileStateStore  # noqa: E402


class AuditWaveProfileTests(unittest.TestCase):
    def test_export_is_idempotent_after_jsonl_already_contains_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            try:
                append_jsonl(jsonl, {"packet_id": "p1", "export_sequence": 1})
                with store.db:
                    store.db.execute(
                        """
                        INSERT INTO jsonl_export_queue(target, payload_json, created_utc)
                        VALUES (?, ?, ?)
                        """,
                        (
                            str(jsonl),
                            json.dumps({"packet_id": "p1"}, separators=(",", ":")),
                            "2026-08-24T12:00:00Z",
                        ),
                    )
                self.assertTrue(jsonl_contains_sequence(jsonl, 1))
                exported = store.export_pending_jsonl(jsonl)
                self.assertEqual(exported, 0)
                self.assertEqual(store.export_backlog_count(jsonl), 0)
                self.assertEqual(len(jsonl.read_text(encoding="utf-8").strip().splitlines()), 1)
            finally:
                store.close()

    def test_sync_cursor_waits_for_complete_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            jsonl.write_text(
                json.dumps({"packet_id": "p0", "recorded_utc": "2026-08-24T12:00:00Z"})
                + "\n"
                + '{"packet_id":"partial"',
                encoding="utf-8",
            )
            store = ProfileStateStore(state)
            try:
                store.sync_decisions_from_jsonl(jsonl)
                self.assertIsNone(store.decision_by_packet("partial"))
                jsonl.write_text(
                    jsonl.read_text(encoding="utf-8") + ',"recorded_utc":"2026-08-24T12:01:00Z"}\n',
                    encoding="utf-8",
                )
                store.sync_decisions_from_jsonl(jsonl)
                self.assertEqual(store.decision_by_packet("partial")["packet_id"], "partial")
            finally:
                store.close()

    def test_prune_preserves_referenced_minute_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            frames = state / "minute-frames"
            frames.mkdir(parents=True)
            referenced = frames / "old-ref.json"
            referenced.write_text("{}", encoding="utf-8")
            stale = frames / "old-stale.json"
            stale.write_text("{}", encoding="utf-8")
            (state / "outbox").mkdir()
            (state / "outbox" / "old-ref.json").write_text("{}", encoding="utf-8")
            from datetime import datetime, timedelta, timezone

            old = datetime.now(timezone.utc) - timedelta(hours=96)
            referenced.touch()
            stale.touch()
            import os

            os.utime(referenced, (old.timestamp(), old.timestamp()))
            os.utime(stale, (old.timestamp(), old.timestamp()))
            result = prune_state_retention(state, now=datetime.now(timezone.utc))
            self.assertTrue(referenced.is_file())
            self.assertFalse(stale.is_file())
            self.assertEqual(result.get("minute_frames_preserved"), 1)

    def test_run_supervised_times_out_and_returns(self) -> None:
        with self.assertRaises(RuntimeError):
            run_supervised(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
