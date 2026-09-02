"""Tests for frozen cohort manifest verification."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "verify_frozen_cohort",
    SCRIPTS / "verify-frozen-cohort.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

MANIFEST = ROOT / "evaluation" / "runs" / "frozen-cohort-manifest-2026-09-01.json"


class VerifyFrozenCohortTests(unittest.TestCase):
    def test_manifest_present(self) -> None:
        self.assertTrue(MANIFEST.is_file(), f"missing manifest: {MANIFEST}")

    def test_verify_passes_on_current_repo(self) -> None:
        report = _mod.verify_frozen_cohort(manifest_path=MANIFEST, repo_root=ROOT)
        self.assertTrue(report.get("ok"), report)
        self.assertEqual(report.get("file_hash_drifts"), [])
        self.assertEqual(report.get("version_drifts"), [])

    def test_collection_queue_has_six_envelopes(self) -> None:
        import json

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        queue = manifest.get("collection_queue") or []
        self.assertEqual(len(queue), 6)
        tags = {row["scenario_tag"] for row in queue}
        self.assertIn("operator_minute_frame", tags)
        self.assertIn("timeout", tags)
        self.assertNotIn("prac_directed_test", tags)

    def test_historical_cohorts_excluded(self) -> None:
        import json

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        historical = manifest.get("historical_cohorts") or {}
        self.assertTrue(historical.get("excluded_from_new_collection_population"))
        self.assertEqual(
            set(historical.get("runs") or []),
            {"r7-contract", "r8-contract", "r9-v2"},
        )

    def test_detects_hash_drift(self) -> None:
        import json
        import tempfile

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["frozen_file_hashes"]["evaluation/registry.json"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            for rel_path in manifest["frozen_file_hashes"]:
                src = ROOT / rel_path
                dest = tmp_root / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
            manifest_path = tmp_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = _mod.verify_frozen_cohort(manifest_path=manifest_path, repo_root=tmp_root)
            self.assertFalse(report.get("ok"))
            self.assertTrue(report.get("file_hash_drifts"))


if __name__ == "__main__":
    unittest.main()
