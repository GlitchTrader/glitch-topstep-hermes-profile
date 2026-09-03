"""Ownership spec tests for OwnerKind=evaluation (spec-only; implementation pending)."""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(SCRIPTS))

from model_owner_lock import OwnerKind, PRIORITY  # noqa: E402


def _load_json(name: str) -> dict:
    return json.loads((EVAL / "schemas" / name).read_text(encoding="utf-8"))


class EvaluationOwnershipSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = _load_json("ownership_evaluation.v1.json")
        self.prac_chain = _load_json("prac_evidence_chain.v1.json")

    def test_spec_declares_implemented(self) -> None:
        self.assertEqual(self.spec["owner_kind"], "evaluation")
        self.assertEqual(self.spec["status"], "implemented")

    def test_evaluation_in_owner_kind_with_priority_40(self) -> None:
        kinds = set(get_args(OwnerKind))
        self.assertIn("evaluation", kinds)
        self.assertEqual(PRIORITY["evaluation"], 40)
        self.assertEqual(self.spec["priority"]["evaluation"], PRIORITY["evaluation"])

    def test_spec_priority_order_vs_direct_cycle_and_learning(self) -> None:
        p = self.spec["priority"]
        self.assertGreater(p["direct_cycle"], p["evaluation"])
        self.assertGreater(p["evaluation"], p["learning"])
        self.assertGreater(PRIORITY["direct_cycle"], PRIORITY["learning"])

    def test_spec_forbids_production_state_paths(self) -> None:
        forbidden = set(self.spec["state_root"]["forbidden_production_paths"])
        self.assertIn("state/decisions.jsonl", forbidden)
        self.assertIn("state/receipts.jsonl", forbidden)
        self.assertIn("state/outbox", forbidden)
        self.assertIn("state/model-owner.lock", forbidden)

    def test_hermes_home_must_differ_from_production(self) -> None:
        home = self.spec["hermes_home"]
        self.assertTrue(home["must_not_equal_production"])
        self.assertNotEqual(
            home["production_path_pattern"],
            home["evaluation_path_pattern"],
        )

    def test_cognitive_replay_blocked_artifact_replay_allowed(self) -> None:
        replay = self.spec["replay_kinds"]
        self.assertFalse(replay["cognitive_replay"]["allowed_now"])
        self.assertTrue(replay["artifact_replay"]["allowed_now"])
        self.assertFalse(replay["artifact_replay"]["invokes_hermes"])
        self.assertTrue(replay["cognitive_replay"]["invokes_hermes"])

    def test_cognitive_replay_requires_owner_kind_before_enable(self) -> None:
        reqs = self.spec["replay_kinds"]["cognitive_replay"]["requires"]
        self.assertTrue(any("OwnerKind=evaluation" in r for r in reqs))

    def test_runner_still_offline_no_model_owner_lock(self) -> None:
        source = (SCRIPTS / "run-ensemble-evaluation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.names[0].name for node in tree.body if isinstance(node, ast.Import)
        }
        imported |= {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        self.assertNotIn("model_owner_lock", imported)

    def test_prac_evidence_chain_required_fields(self) -> None:
        chain = self.prac_chain["required_chain"]
        self.assertEqual(
            chain,
            [
                "packet_id",
                "market_snapshot_hash",
                "intent_id",
                "decision_record",
                "receipt",
            ],
        )
        exports = self.prac_chain["session_exports"]
        self.assertTrue(exports["decisions_jsonl"]["required"])
        self.assertTrue(exports["evidence_chain_manifest"]["required"])

    def test_production_lane_active_never_submits_intents(self) -> None:
        prod = self.spec["production_lane_active"]
        self.assertTrue(prod["never_submit_gateway_intents"])
        self.assertTrue(prod["never_write_production_state"])


if __name__ == "__main__":
    unittest.main()
