"""Tests for parallel gate task isolation."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from parallel_gate_isolation import (  # noqa: E402
    aggregate_parallel_results,
    cleanup_isolated_gate,
    prepare_isolated_gate_env,
)


class ParallelGateIsolationTests(unittest.TestCase):
    def test_exclusive_hermes_home_and_data_dir_per_task(self) -> None:
        env_a, ctx_a = prepare_isolated_gate_env("task_a")
        env_b, ctx_b = prepare_isolated_gate_env("task_b")
        self.assertNotEqual(env_a["EVALUATION_HERMES_HOME"], env_b["EVALUATION_HERMES_HOME"])
        self.assertNotEqual(env_a["GLITCH_DATA_DIR"], env_b["GLITCH_DATA_DIR"])
        self.assertEqual(env_a["HERMES_HOME"], env_a["EVALUATION_HERMES_HOME"])
        self.assertTrue(Path(env_a["EVALUATION_HERMES_HOME"]).is_dir())
        self.assertTrue(Path(env_a["GLITCH_DATA_DIR"]).is_dir())
        cleanup_isolated_gate(ctx_a)
        cleanup_isolated_gate(ctx_b)

    def test_aggregate_fails_closed_on_any_nonzero_exit(self) -> None:
        summary = aggregate_parallel_results(
            [
                {"task_id": "ok", "exit_code": 0},
                {"task_id": "bad", "exit_code": 1},
            ]
        )
        self.assertFalse(summary["all_pass"])
        self.assertIn("bad", summary["failed_tasks"])

    def test_aggregate_fails_on_missing_exit_code(self) -> None:
        summary = aggregate_parallel_results([{"task_id": "timeout", "exit_code": None}])
        self.assertFalse(summary["all_pass"])


if __name__ == "__main__":
    unittest.main()
