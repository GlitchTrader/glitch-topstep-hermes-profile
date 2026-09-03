"""Security tests for allowlisted evaluation run bundle persistence."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evaluation_run_public_bundle import (  # noqa: E402
    bundle_text_forbidden_sentinels,
    persist_public_run_bundle,
    public_profile_slot,
    public_run_bundle,
)

SENTINELS = (
    "TEST_EVALUATION_SECRET",
    "TEST_API_KEY",
    "Authorization: Bearer leaked",
)


def _normalized(profile_id: str = "baseline-current") -> dict:
    return {
        "schema_version": "glitch.topstep.normalized_candidate.v1",
        "run_id": "run-1",
        "profile_id": profile_id,
        "profile_version": "2026-09-02-v1",
        "invocation_id": f"inv-{profile_id}",
        "envelope_id": "env-abc",
        "envelope_hash": "hash-env",
        "state": "no_edge",
        "comparability": "comparable",
        "profile_declared_state": "no_edge",
        "profile_declared_direction": "flat",
        "capacity_gate_reason": None,
        "instrument": "MNQ",
        "direction": "flat",
        "latency_ms": 120,
        "started_utc": "2026-09-02T12:00:00Z",
        "finished_utc": "2026-09-02T12:00:01Z",
    }


def _artifact_row(
    *,
    profile_id: str = "baseline-current",
    status: str = "completed",
    extra: dict | None = None,
) -> dict:
    artifact = {
        "schema_version": "glitch.topstep.minimal_cognitive_replay.v1",
        "status": status,
        "profile_id": profile_id,
        "invocation_id": f"inv-{profile_id}",
        "snapshot_hash": "snap-1",
        "envelope_hash": "hash-env",
        "latency_ms": 120,
        "cost_usd": 0.01,
        "model": "test-model",
        "provider": "openrouter",
        "normalized": _normalized(profile_id),
        "raw_profile_output": {"state": "no_edge"},
        "credentials": {"EVALUATION_OPENROUTER_API_KEY": "TEST_EVALUATION_SECRET"},
        "environment": {"TEST_API_KEY": "TEST_API_KEY", "Authorization": "Bearer leaked"},
        "subprocess_env": {"OPENROUTER_API_KEY": "TEST_EVALUATION_SECRET"},
    }
    if extra:
        artifact.update(extra)
    return {
        "profile_id": profile_id,
        "invocation_id": f"inv-{profile_id}",
        "artifact_path": str(ROOT / "evaluation" / "runs" / f"{profile_id} artifact.json"),
        "artifact": artifact,
        "work_dir": str(ROOT / "evaluation" / "state" / "secret-session"),
    }


class TrailABundleSanitizationTests(unittest.TestCase):
    def _persist_and_read(self, result: dict) -> tuple[dict, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle.json"
            persist_public_run_bundle(result, path)
            text = path.read_text(encoding="utf-8")
            return json.loads(text), text

    def test_sentinels_not_in_persisted_bundle(self) -> None:
        result = {
            "schema_version": "glitch.topstep.trail_a_parallel_live_run.v1",
            "status": "completed",
            "run_id": "sentinel-test",
            "profile_slots": [_artifact_row()],
        }
        _, text = self._persist_and_read(result)
        self.assertEqual(bundle_text_forbidden_sentinels(text, SENTINELS), [])

    def test_artifact_absent(self) -> None:
        slot = public_profile_slot(
            {
                "profile_id": "structure",
                "invocation_id": "inv-structure",
                "status": "completed",
                "artifact_path": "C:/runs/structure.json",
                "normalized": _normalized("structure"),
                "latency_ms": 50,
            }
        )
        self.assertNotIn("artifact", slot)
        self.assertEqual(slot["profile_id"], "structure")

    def test_artifact_extra_fields_stripped(self) -> None:
        slot = public_profile_slot(_artifact_row())
        self.assertNotIn("artifact", slot)
        self.assertNotIn("work_dir", slot)
        self.assertNotIn("credentials", slot)
        self.assertNotIn("environment", slot)
        self.assertNotIn("raw_profile_output", slot)

    def test_provider_error_classified(self) -> None:
        row = _artifact_row(status="failed", extra={"reason": "profile_error:provider:timeout"})
        slot = public_profile_slot(row)
        self.assertEqual(slot["status"], "failed")
        self.assertEqual(slot["error_class"], "provider_error")

    def test_timeout_error_classified(self) -> None:
        row = _artifact_row(status="timeout", extra={"error_code": "hermes_timeout"})
        slot = public_profile_slot(row)
        self.assertEqual(slot["error_class"], "timeout")

    def test_normal_profile_fields(self) -> None:
        bundle, text = self._persist_and_read(
            {
                "schema_version": "glitch.topstep.trail_a_parallel_live_run.v1",
                "status": "completed",
                "run_id": "normal",
                "profile_slots": [_artifact_row()],
                "selection": {"outcome": "no_selection", "decision_code": "ENSEMBLE_UNANIMOUS_ABSTENTION"},
            }
        )
        slot = bundle["profile_slots"][0]
        self.assertEqual(slot["status"], "completed")
        self.assertIn("normalized", slot)
        self.assertEqual(slot["normalized"]["state"], "no_edge")
        self.assertEqual(bundle_text_forbidden_sentinels(text, SENTINELS), [])

    def test_multiple_profiles(self) -> None:
        bundle = public_run_bundle(
            {
                "schema_version": "glitch.topstep.trail_a_parallel_live_run.v1",
                "status": "completed",
                "run_id": "multi",
                "profile_slots": [
                    _artifact_row(profile_id="baseline-current"),
                    _artifact_row(profile_id="structure"),
                    _artifact_row(profile_id="adversarial-risk"),
                ],
            }
        )
        self.assertEqual(len(bundle["profile_slots"]), 3)
        self.assertTrue(all("artifact" not in slot for slot in bundle["profile_slots"]))

    def test_partial_failure_frame(self) -> None:
        bundle = public_run_bundle(
            {
                "schema_version": "glitch.topstep.trail_a_multi_envelope_live_run.v1",
                "status": "failed",
                "run_id": "partial",
                "frame_results": [
                    {
                        "status": "failed",
                        "reason": "profile_incomplete:frame:structure",
                        "scenario_id": "S1",
                        "frame_id": "f1",
                        "profile_slots": [
                            _artifact_row(profile_id="baseline-current"),
                            _artifact_row(profile_id="structure", status="failed", extra={"reason": "timeout"}),
                        ],
                    }
                ],
            }
        )
        failed_slot = bundle["frame_results"][0]["profile_slots"][1]
        self.assertEqual(failed_slot["error_class"], "timeout")

    def test_windows_path_with_spaces(self) -> None:
        spaced = r"C:\Users\arifr\Projects\glitch topstep\evaluation runs\profile one.json"
        bundle, text = self._persist_and_read(
            {
                "schema_version": "glitch.topstep.trail_a_parallel_live_run.v1",
                "status": "completed",
                "run_id": "path-space",
                "profile_slots": [
                    {
                        "profile_id": "baseline-current",
                        "artifact_path": spaced,
                        "artifact": _artifact_row()["artifact"],
                    }
                ],
            }
        )
        self.assertEqual(bundle["profile_slots"][0]["artifact_path"], spaced)
        self.assertEqual(bundle_text_forbidden_sentinels(text, SENTINELS), [])

    def test_preflight_check_detail_stripped(self) -> None:
        public = public_run_bundle(
            {
                "preflight": {
                    "verdict": "PASS",
                    "checks": [{"id": "lease", "ok": True, "detail": "TEST_EVALUATION_SECRET"}],
                }
            }
        )
        self.assertEqual(public["preflight"]["checks"][0], {"id": "lease", "ok": True})


class TrailALivePersistIntegrationTests(unittest.TestCase):
    def test_persist_public_bundle_strips_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            persist_public_run_bundle(
                {
                    "schema_version": "glitch.topstep.trail_a_parallel_live_run.v1",
                    "status": "completed",
                    "run_id": "persist-test",
                    "profile_slots": [_artifact_row()],
                },
                out,
            )
            text = out.read_text(encoding="utf-8")
            self.assertEqual(bundle_text_forbidden_sentinels(text, SENTINELS), [])
            self.assertNotIn('"artifact"', text)


if __name__ == "__main__":
    unittest.main()
