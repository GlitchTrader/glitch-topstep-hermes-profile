import json
import os
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from model_owner_lock import (  # noqa: E402
    acquire_model_owner,
    read_model_owner,
    release_model_owner,
    model_owner_lock_path,
)


class ModelOwnerLockTests(unittest.TestCase):
    def test_direct_cycle_acquires_and_releases(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="direct_cycle",
                    invocation_id="run-1",
                )
            )
            owner = read_model_owner(model_owner_lock_path(state))
            self.assertEqual(owner["owner_kind"], "direct_cycle")
            release_model_owner(state, owner_kind="direct_cycle", invocation_id="run-1")
            self.assertIsNone(read_model_owner(model_owner_lock_path(state)))

    def test_learning_defers_while_direct_cycle_active(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="direct_cycle",
                    invocation_id="run-direct",
                )
            )
            self.assertFalse(
                acquire_model_owner(
                    state,
                    owner_kind="learning",
                    invocation_id="run-learning",
                )
            )
            release_model_owner(state, owner_kind="direct_cycle", invocation_id="run-direct")
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="learning",
                    invocation_id="run-learning",
                )
            )


    def test_evaluation_acquires_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="run-eval",
                )
            )
            owner = read_model_owner(model_owner_lock_path(state))
            assert isinstance(owner, dict)
            self.assertEqual(owner["owner_kind"], "evaluation")
            self.assertEqual(owner["priority"], 40)
            release_model_owner(state, owner_kind="evaluation", invocation_id="run-eval")
            self.assertIsNone(read_model_owner(model_owner_lock_path(state)))


if __name__ == "__main__":
    unittest.main()
