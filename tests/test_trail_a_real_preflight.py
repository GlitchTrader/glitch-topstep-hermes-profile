"""Tests for Trilha A real run preflight (no Hermes invoke)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = _load("run_trail_a_real_preflight", "run-trail-a-real-preflight.py")


class TrailARealPreflightTests(unittest.TestCase):
    def test_pinned_envelope_validates(self) -> None:
        from common import read_json

        config = read_json(ROOT / "evaluation" / "trail-a-real-run-config.v1.json")
        scenarios = read_json(ROOT / "evaluation" / "trail-a-real-scenarios.v1.json")
        matrix = read_json(ROOT / "evaluation" / "capability-matrix.json")
        mapping = read_json(ROOT / "evaluation" / "packet_envelope_mapping.v1.json")
        result = PREFLIGHT.validate_pinned_envelope(
            config=config, scenarios=scenarios, matrix=matrix, mapping=mapping
        )
        self.assertTrue(result["ok"], result.get("issues"))

    def test_live_runner_without_authorize_does_not_invoke(self) -> None:
        LIVE = _load("run_trail_a_parallel_live", "run-trail-a-parallel-live-evaluation.py")
        result = LIVE.run_trail_a_parallel_live(
            run_id="trail-a-dry-run-test",
            authorize=False,
        )
        self.assertEqual(result.get("status"), "awaiting_human_authorization")


if __name__ == "__main__":
    unittest.main()
