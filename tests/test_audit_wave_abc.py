"""Tests for audit wave A/B profile remediation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import append_jsonl, jsonl_contains_sequence  # noqa: E402
from process_supervisor import run_supervised  # noqa: E402
import process_supervisor as process_supervisor_module  # noqa: E402
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
        import subprocess as sp

        mock_proc = mock.MagicMock()
        mock_proc.stdin = mock_proc.stdout = mock_proc.stderr = None
        mock_proc.communicate.side_effect = sp.TimeoutExpired(cmd="cmd", timeout=1)
        with mock.patch.object(
            process_supervisor_module.subprocess, "Popen", return_value=mock_proc
        ):
            with mock.patch.object(
                process_supervisor_module, "terminate_process_tree"
            ) as terminate:
                with self.assertRaises(RuntimeError):
                    run_supervised(["ignored"], timeout_seconds=1)
                terminate.assert_called_once_with(mock_proc)


if __name__ == "__main__":
    unittest.main()
