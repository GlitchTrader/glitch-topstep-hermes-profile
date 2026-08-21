import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import bootstrap_profile_state
from state_store import ProfileStateStore


    def test_bootstrap_profile_state_indexes_decisions_before_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            jsonl.write_text(
                '{"schema_version":"glitch.topstep.decision_record.v2",'
                '"recorded_utc":"2026-08-21T00:00:00Z","packet_id":"pkt-1",'
                '"intent":{"action":"NOTHING"}}\n',
                encoding="utf-8",
            )
            with mock.patch(
                "common.sync_gateway_outcomes_meta",
                return_value={"added": 2, "http_status": 200},
            ) as sync_mock:
                result = bootstrap_profile_state(state)
            sync_mock.assert_called_once_with(state)
            self.assertEqual(result["added"], 2)
            store = ProfileStateStore(state)
            try:
                rows = store.tail_decisions(10)
            finally:
                store.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["packet_id"], "pkt-1")

    def test_load_parent_hermes_provider_env_fills_missing_openrouter_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "hermes"
            parent.mkdir()
            (parent / ".env").write_text(
                "OPENROUTER_API_KEY=parent-key\nOTHER=value\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}, clear=False):
                os.environ.pop("OPENROUTER_API_KEY", None)
                from common import load_parent_hermes_provider_env

                load_parent_hermes_provider_env()
                self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), "parent-key")
            os.environ.pop("OPENROUTER_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
