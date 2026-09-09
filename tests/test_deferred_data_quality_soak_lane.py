from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deferred_data_quality_soak_lane import (  # noqa: E402
    DEFERRED_DATA_QUALITY,
    VALID_CYCLE,
    advance_lane_checkpoint,
    checkpoint_payload,
    load_lane_config,
    persist_lane_checkpoint,
)


class DeferredDataQualitySoakLaneTests(unittest.TestCase):
    def test_config_requires_six_profiles_two_slots_and_no_execution_authority(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        self.assertEqual(len(config["profiles"]), 6)
        self.assertEqual(config["budget"]["max_parallel_slots"], 2)
        self.assertTrue(all(p["execution_authority"] is False for p in config["profiles"]))
        self.assertFalse(config.get("auto_start_prac"))
        defaults = config["bar_close_acceptance_v2_defaults"]
        self.assertEqual(defaults["required_samples"], 5)
        self.assertEqual(defaults["post_close_window_seconds"], 5)
        self.assertEqual(defaults["provider_roll_latency_seconds"], 10)
        self.assertEqual(defaults["max_total_boundaries"], 12)
        self.assertEqual(defaults["max_total_duration_seconds"], 720)
        self.assertIn("run-trail-a-parallel-live-evaluation.py", config["reuses_existing_lane"]["runner"])

    def test_t0_starts_only_after_first_valid_cycle(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        checkpoint = checkpoint_payload(config, run_id="soak-v2")
        deferred = advance_lane_checkpoint(
            checkpoint,
            cycle_id="cycle-1",
            cycle_status=DEFERRED_DATA_QUALITY,
            packet_id="pkt-1",
            now_utc="2026-09-09T16:00:00Z",
        )
        self.assertIsNone(deferred["t0_utc"])
        self.assertEqual(deferred["status"], "awaiting_first_valid_cycle")
        valid = advance_lane_checkpoint(
            deferred,
            cycle_id="cycle-2",
            cycle_status=VALID_CYCLE,
            packet_id="pkt-2",
            now_utc="2026-09-09T16:01:00Z",
        )
        self.assertEqual(valid["t0_utc"], "2026-09-09T16:01:00Z")
        self.assertEqual(valid["first_valid_cycle_id"], "cycle-2")
        self.assertEqual(valid["deferred_cycles"], 1)
        self.assertEqual(valid["valid_cycles"], 1)

    def test_checkpoint_round_trip_supports_resume(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        checkpoint = checkpoint_payload(config, run_id="soak-v2")
        checkpoint = advance_lane_checkpoint(
            checkpoint,
            cycle_id="cycle-2",
            cycle_status=VALID_CYCLE,
            packet_id="pkt-2",
            now_utc="2026-09-09T16:01:00Z",
        )
        with tempfile.TemporaryDirectory() as tmp:
            payload = persist_lane_checkpoint(Path(tmp), checkpoint)
            self.assertEqual(payload["resume_token"], "cycle-2")
            self.assertEqual(payload["first_valid_cycle_id"], "cycle-2")


if __name__ == "__main__":
    unittest.main()
