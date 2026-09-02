"""Phase 7 shadow live safety tests — evaluation lane, zero operational writes."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
FIXTURES = ROOT / "tests" / "fixtures"
FRAME = FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PACKAGE = _load("build_package", "build-evaluation-release-package.py")
PREFLIGHT = _load("shadow_preflight", "shadow-preflight.py")
SHADOW_LIVE = _load("shadow_observe_live", "shadow-observe-live.py")
SHADOW_OFFLINE = _load("shadow_observe_offline", "shadow-observe-offline.py")
METRICS = _load("report_shadow_metrics", "report-shadow-metrics.py")
ISOLATION = _load("audit_shadow_isolation", "audit-shadow-isolation.py")
MEASUREMENT = _load("evaluation_measurement_ready", "evaluation-measurement-ready.py")
OBSERVATION = _load("shadow_observation", "shadow_observation.py")


def _good_health() -> dict:
    return {
        "status": "ok",
        "lifecycle": {"state": "ready"},
        "data_quality": {
            "state_complete": True,
            "operational": {
                "marketStream": {"state": "connected"},
                "userStream": {"state": "connected"},
                "reconciliation": {"state": "succeeded"},
            },
        },
    }


def _maintenance_health() -> dict:
    health = _good_health()
    health["status"] = "degraded"
    return health


def _good_packet() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "packet_id": "pkt-shadow",
        "instrument": "MNQ",
        "created_utc": now.isoformat().replace("+00:00", "Z"),
        "execution": {"daily_capture_locked": False},
        "data_quality": {"state_complete": True},
        "market": {
            "instrument": "MNQ",
            "quote_valid": True,
            "quote_timestamp": now.isoformat().replace("+00:00", "Z"),
        },
        "market_observation": {
            "observation": {
                "timeframes": [
                    {
                        "timeframe_minutes": 1,
                        "latest_bar_utc": (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
                        "latest_bar_partial": False,
                    }
                ]
            }
        },
    }


class ReleasePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = PACKAGE.build_release_package(package_id="test-package")
        out = EVAL / "release" / "six-profile-evaluation-package-2026-09-02.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cls.package, indent=2) + "\n", encoding="utf-8")

    def test_six_profiles_and_safety_flags(self) -> None:
        self.assertTrue(self.package["valid"])
        self.assertEqual(self.package["profile_count"], 6)
        flags = self.package["safety_flags"]
        self.assertTrue(flags["execution_authority_false_all"])
        self.assertEqual(flags["production_parallelism"], "blocked")
        self.assertFalse(flags["promotion_use_allowed"])


class ShadowPreflightTests(unittest.TestCase):
    def test_maintenance_window_blocks_without_gateway_start(self) -> None:
        result = PREFLIGHT.shadow_preflight(
            run_id="test-shadow-preflight",
            gateway_health=_maintenance_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "shadow_not_ready:maintenance_window")
        self.assertFalse(result["gateway_started"])
        self.assertFalse(result["hermes_started"])

    @patch.object(PREFLIGHT, "_load_replay_preflight")
    @patch.object(PREFLIGHT, "ensure_evaluation_auth_ready", return_value=(True, None))
    def test_good_health_preflight_structure(self, _auth, mock_replay_loader) -> None:
        mock_replay_loader.return_value = lambda **_: {
            "ok": True,
            "checks": [{"id": "evaluation_lease_available", "ok": True}],
        }
        replay_mod = type("M", (), {"preflight_evaluation_replay": staticmethod(lambda **_: {"ok": True})})
        with patch.object(PREFLIGHT, "_load_replay_preflight", return_value=replay_mod):
            result = PREFLIGHT.shadow_preflight(
                run_id="test-shadow-preflight",
                gateway_health=_good_health(),
                packet=_good_packet(),
            )
        self.assertFalse(result["shadow_live_execution_authorized"])
        self.assertFalse(result["promotion_use_allowed"])
        self.assertEqual(result["production_parallelism"], "blocked")

    def test_daily_capture_locked_in_capture_mode(self) -> None:
        packet = _good_packet()
        packet["execution"]["daily_capture_locked"] = True
        result = MEASUREMENT.evaluation_measurement_ready(
            mode="capture",
            packet=packet,
            gateway_health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertIn("daily_capture_locked", result["blocking_reasons"])

    def test_state_complete_false(self) -> None:
        health = _good_health()
        health["data_quality"]["state_complete"] = False
        result = MEASUREMENT.evaluation_measurement_ready(mode="preflight", gateway_health=health)
        self.assertIn("gateway_state_incomplete", result["blocking_reasons"])

    def test_partial_bar(self) -> None:
        packet = _good_packet()
        packet["market_observation"]["observation"]["timeframes"][0]["latest_bar_partial"] = True
        result = MEASUREMENT.evaluation_measurement_ready(
            mode="capture",
            packet=packet,
            gateway_health=_good_health(),
        )
        self.assertIn("bar_1m_partial", result["blocking_reasons"])


class ShadowObserverTests(unittest.TestCase):
    def test_offline_prep_six_profiles_zero_writes(self) -> None:
        session = SHADOW_LIVE.run_shadow_offline_prep(run_id="test-shadow-offline-six")
        self.assertEqual(session["status"], "offline_prep_complete")
        obs = session["observation"]
        self.assertEqual(obs["intents_sent"], 0)
        self.assertEqual(obs["orders_sent"], 0)
        self.assertEqual(obs["writes_operacionais"], 0)
        self.assertEqual(len(obs["profile_decisions"]), 6)
        self.assertIn("aggregator_selection", obs)
        self.assertIn("envelope", obs)
        self.assertIsNotNone(obs["envelope"].get("snapshot_hash"))

    def test_blocked_without_authorization(self) -> None:
        blocked = SHADOW_LIVE.run_shadow_session(run_id="test-blocked", authorize=False)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["intents_sent"], 0)

    def test_observation_records_no_selection_fields(self) -> None:
        session = SHADOW_LIVE.run_shadow_offline_prep(run_id="test-no-selection-fields")
        agg = session["observation"]["aggregator_selection"]
        self.assertIn("outcome", agg)
        self.assertIn("decision_code", agg)
        if agg["outcome"] == "no_selection":
            self.assertIsNotNone(agg.get("no_selection_reason"))

    def test_isolation_audit_passes_offline(self) -> None:
        session = SHADOW_LIVE.run_shadow_offline_prep(run_id="test-isolation")
        report = ISOLATION.audit_shadow_session(session)
        self.assertTrue(report["valid"])


class ShadowSafetyScenarioTests(unittest.TestCase):
    def test_gateway_unavailable_measurement(self) -> None:
        result = MEASUREMENT.evaluation_measurement_ready(mode="preflight", gateway_health=None, packet=None)
        self.assertIn("market_not_valid", result["blocking_reasons"])

    def test_aggregator_no_selection_fixture(self) -> None:
        cases = json.loads(
            (EVAL / "fixtures" / "aggregator_decision_cases_six_profiles.v1.json").read_text(encoding="utf-8")
        )
        all_no_edge = next(c for c in cases["cases"] if c["case_id"] == "SIX-NO-EDGE-01")
        self.assertEqual(all_no_edge["expected"]["result"], "no_selection")

    def test_build_shadow_observation_zero_writes(self) -> None:
        obs = OBSERVATION.build_shadow_observation(
            run_id="t",
            envelope={"snapshot_hash": "a", "envelope_hash": "b"},
            profile_decisions=[],
            candidates=[],
            selection={"outcome": "no_selection", "decision_code": "ALL_NO_EDGE"},
            baseline_id="baseline-current",
            cost_usd=0.01,
            latency_ms_total=10,
            shadow_live=False,
        )
        self.assertEqual(obs["writes_operacionais"], 0)
        self.assertEqual(obs["intents_sent"], 0)

    def test_metrics_report_from_sessions(self) -> None:
        session = SHADOW_LIVE.run_shadow_offline_prep(run_id="test-metrics")
        out = ROOT / "evaluation" / "runs" / "test-shadow-metrics-temp.json"
        out.write_text(json.dumps(session, indent=2), encoding="utf-8")
        report = METRICS.build_shadow_metrics_report(observation_paths=[out])
        self.assertGreaterEqual(report["session_count"], 1)
        self.assertEqual(report["operational_writes_total"], 0)
        self.assertFalse(report["promotion_use_allowed"])
        out.unlink(missing_ok=True)

    def test_operational_write_detection(self) -> None:
        obs = OBSERVATION.build_shadow_observation(
            run_id="t",
            envelope={"snapshot_hash": "a", "envelope_hash": "b"},
            profile_decisions=[],
            candidates=[],
            selection={"outcome": "no_selection"},
            baseline_id="baseline-current",
            cost_usd=0,
            latency_ms_total=0,
            shadow_live=True,
            operational_writes_detected=True,
        )
        audit = ISOLATION.audit_shadow_observation(obs)
        self.assertFalse(audit["valid"])
        self.assertIn("writes_operacionais_nonzero", audit["issues"])


if __name__ == "__main__":
    unittest.main()
