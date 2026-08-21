"""Tests for cycle empirical sampling (Trail D)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cycle_empirical import empirical_from_decision, record_cycle_empirical  # noqa: E402


class CycleEmpiricalTests(unittest.TestCase):
    def test_record_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            record_cycle_empirical(
                state,
                empirical_from_decision(
                    packet={"packet_id": "p1", "instrument": "MNQ", "account": {}},
                    intent={
                        "packet_id": "p1",
                        "instrument": "MNQ",
                        "action": "NOTHING",
                        "confidence": 0.78,
                    },
                    invocation_reason="retry_after_failure",
                    phase="decision_ready",
                ),
            )
            path = state / "cycle-empirical.jsonl"
            self.assertTrue(path.is_file())
            row = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["schema_version"], "glitch.topstep.cycle_empirical.v1")
            self.assertEqual(row["action"], "NOTHING")
            self.assertEqual(row["phase"], "decision_ready")


if __name__ == "__main__":
    unittest.main()
