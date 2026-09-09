from __future__ import annotations

import json
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
    SoakLeaseError,
    advance_lane_checkpoint,
    checkpoint_payload,
    heartbeat_soak_evaluation_lease,
    load_lane_config,
    persist_lane_checkpoint,
    require_soak_evaluation_lease,
)
from evaluation_lease import (  # noqa: E402
    acquire_evaluation_lease,
    evaluation_lease_active,
    read_evaluation_lease,
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

    def test_require_lease_fail_closed_when_unavailable(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            self.assertTrue(
                acquire_evaluation_lease(state, run_id="foreign", invocation_id="other", ttl_seconds=120)
            )
            with self.assertRaises(SoakLeaseError):
                require_soak_evaluation_lease(
                    config=config,
                    run_id="soak-new",
                    production_state=state,
                    ttl_seconds=120,
                )

    def test_require_lease_acquire_heartbeat_release(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            acquired = require_soak_evaluation_lease(
                config=config,
                run_id="soak-lease-1",
                production_state=state,
                ttl_seconds=90,
            )
            self.assertTrue(acquired["lease_id"])
            self.assertEqual(acquired["run_id"], "soak-lease-1")
            self.assertTrue(evaluation_lease_active(state))
            lease = read_evaluation_lease(state)
            assert lease is not None
            self.assertEqual(lease["lease_id"], acquired["lease_id"])
            self.assertIn("owner", lease)
            self.assertIn("ttl_seconds", lease)
            hb = heartbeat_soak_evaluation_lease(
                production_state=state,
                run_id="soak-lease-1",
                invocation_id=str(acquired["owner_invocation_id"]),
                ttl_seconds=90,
            )
            self.assertEqual(hb["lease_id"], acquired["lease_id"])
            acquired["holder"].release()
            self.assertFalse(evaluation_lease_active(state))
            self.assertIsNone(read_evaluation_lease(state))

    def test_absent_lease_is_not_valid_execution(self) -> None:
        config = load_lane_config(ROOT / "evaluation" / "deferred-data-quality-soak-lane.v1.json")
        self.assertIs(config["isolation"]["lease_required"], True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-config.json"
            bad = dict(config)
            bad["isolation"] = {"lease_required": False, "hermes_home_isolated": True}
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_lane_config(path)


if __name__ == "__main__":
    unittest.main()
