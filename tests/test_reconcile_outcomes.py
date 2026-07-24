import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("reconcile_topstep_outcomes", SCRIPTS / "reconcile_topstep_outcomes.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReconcileOutcomesTests(unittest.TestCase):
    def test_enrich_marks_shadow_receipts_not_learning_eligible(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            state = root / "state"
            packet_id = "20260101T120000Z"
            intent_id = "11111111-1111-1111-1111-111111111111"
            (state / "outbox").mkdir(parents=True)
            (state / "receipts").mkdir(parents=True)
            intent = {
                "intent_id": intent_id,
                "action": "ENTER_LONG",
                "quantity": 1,
                "stop_loss": 100,
                "take_profit_1": 110,
            }
            (state / "outbox" / f"{packet_id}.json").write_text(json.dumps(intent), encoding="utf-8")
            (state / "receipts" / f"{packet_id}.json").write_text(json.dumps({
                "intent_id": intent_id,
                "result": {"body": {"shadow_only": True, "trading_mode": "shadow"}},
            }), encoding="utf-8")
            raw_path = root / "state" / "outcomes.jsonl"
            raw_path.write_text(json.dumps({
                "schema_version": "glitch.topstep.trade_outcome.v1",
                "outcome_id": "o1",
                "intent_id": intent_id,
                "account": "acct",
                "instrument": "MNQ",
                "entry_utc": None,
                "exit_utc": "2026-01-01T12:05:00Z",
                "realized_pnl_usd": 10,
                "fees_usd": 1,
                "learning_eligible": True,
            }) + "\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"GLITCH_TOPSTEP_OUTCOMES_PATH": str(raw_path)}, clear=False):
                result = MODULE.reconcile_outcomes(root)
            self.assertEqual(result["canonical_count"], 1)
            rows = read_jsonl(MODULE.outcomes_canonical_path(root))
            self.assertFalse(rows[0]["learning_eligible"])
            self.assertTrue(rows[0]["shadow_only"])


if __name__ == "__main__":
    unittest.main()
