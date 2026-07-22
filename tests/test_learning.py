import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("topstep_learning", SCRIPTS / "run-topstep-learning.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LearningTests(unittest.TestCase):
    def test_only_canonical_learning_eligible_outcomes_are_consumed(self):
        rows = [
            {"schema_version": "glitch.topstep.trade_outcome.v1", "outcome_id": "ok", "intent_id": "i", "account": "a", "instrument": "MNQ", "entry_utc": "2026-01-01T00:00:00Z", "exit_utc": "2026-01-01T00:01:00Z", "realized_pnl_usd": 1, "fees_usd": 0, "learning_eligible": True},
            {"schema_version": "glitch.topstep.trade_outcome.v1", "outcome_id": "bad", "intent_id": "i", "account": "a", "instrument": "MNQ", "entry_utc": "2026-01-01T00:00:00Z", "exit_utc": "2026-01-01T00:01:00Z", "realized_pnl_usd": -1, "fees_usd": 0, "learning_eligible": False},
            {"schema_version": "other", "outcome_id": "other"},
        ]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "outcomes.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            values = MODULE.valid_outcomes(path)
        self.assertEqual([row["outcome_id"] for row in values], ["ok"])

    def test_overlay_is_proposed_by_default(self):
        record = {
            "cognitive_change_candidate": {
                "propose": True,
                "candidate_id": "candidate",
                "target": "core_prompt",
                "instruction": "Prefer exits after repeated failed progress.",
                "evidence_episode_ids": [f"e{i}" for i in range(6)],
                "expected_effect": "less rollback",
                "evaluation_metric": "rollback",
                "rollback_condition": "worse expectancy",
            }
        }
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"GLITCH_TOPSTEP_AUTO_ACTIVATE_OVERLAY": "false", "GLITCH_TOPSTEP_OVERLAY_MIN_EPISODES": "6"}, clear=False):
            supervisor = Path(root)
            MODULE.process_candidate(record, supervisor, [f"e{i}" for i in range(6)])
            candidates = MODULE.read_jsonl(supervisor / "cognitive-candidates.jsonl")
            self.assertEqual(candidates[0]["status"], "proposed")
            self.assertFalse((supervisor / "active-cognitive-overlay.json").exists())

    def test_overlay_requires_configured_evidence_threshold(self):
        record = {
            "cognitive_change_candidate": {
                "propose": True,
                "target": "core_prompt",
                "instruction": "Change",
                "evidence_episode_ids": ["e1", "e2"],
            }
        }
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"GLITCH_TOPSTEP_OVERLAY_MIN_EPISODES": "6"}, clear=False):
            MODULE.process_candidate(record, Path(root), ["e1", "e2"])
            self.assertFalse((Path(root) / "cognitive-candidates.jsonl").exists())

    def test_learning_prompt_keeps_gateway_truth_above_memory(self):
        template = MODULE.output_template("daily", ["j1"])
        prompt = MODULE.prompt_for("daily", {"episodes": []}, template, {})
        self.assertIn("Canonical outcome records and gateway evidence outrank memory", prompt)
        self.assertIn("never manufacture a daily target", prompt)


if __name__ == "__main__":
    unittest.main()
