"""Tests for evaluation-measurement-ready gate."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "evaluation_measurement_ready", SCRIPTS / "evaluation-measurement-ready.py"
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _good_packet() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "packet_id": "pkt-1",
        "instrument": "MNQ",
        "created_utc": now.isoformat().replace("+00:00", "Z"),
        "execution": {"daily_capture_locked": False},
        "data_quality": {"state_complete": True},
        "market": {
            "instrument": "MNQ",
            "quote_valid": True,
            "quote_timestamp": now.isoformat().replace("+00:00", "Z"),
            "last": 100.0,
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


def _good_decision(packet: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "packet_id": packet["packet_id"],
        "recorded_utc": now.isoformat().replace("+00:00", "Z"),
        "intent": {
            "intent_id": "intent-1",
            "packet_id": packet["packet_id"],
            "snapshot_hash": "abc",
            "action": "NOTHING",
            "expires_utc": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        },
    }


def _good_receipt() -> dict:
    return {"intent_id": "intent-1", "packet_id": "pkt-1", "recorded_utc": "2026-09-02T12:00:00Z"}


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
        "recovery": {"active": False},
    }


class EvaluationMeasurementReadyTests(unittest.TestCase):
    @patch.object(mod, "_capacity_ok", return_value=(True, "ok"))
    def test_all_clear_capture_mode(self, _mock_cap: object) -> None:
        packet = _good_packet()
        result = mod.evaluation_measurement_ready(
            mode="capture",
            packet=packet,
            decision=_good_decision(packet),
            receipt=_good_receipt(),
            gateway_health=_good_health(),
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["blocking_reasons"], [])

    def test_daily_capture_locked(self) -> None:
        packet = _good_packet()
        packet["execution"]["daily_capture_locked"] = True
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet)
        self.assertFalse(result["ready"])
        self.assertIn("daily_capture_locked", result["blocking_reasons"])

    def test_gateway_state_incomplete(self) -> None:
        packet = _good_packet()
        packet["data_quality"]["state_complete"] = False
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet)
        self.assertFalse(result["ready"])
        self.assertIn("gateway_state_incomplete", result["blocking_reasons"])

    def test_bar_1m_partial(self) -> None:
        packet = _good_packet()
        packet["market_observation"]["observation"]["timeframes"][0]["latest_bar_partial"] = True
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet)
        self.assertFalse(result["ready"])
        self.assertIn("bar_1m_partial", result["blocking_reasons"])

    def test_bar_1m_lag(self) -> None:
        packet = _good_packet()
        now = datetime.now(timezone.utc)
        packet["market_observation"]["observation"]["timeframes"][0]["latest_bar_utc"] = (
            now - timedelta(minutes=5)
        ).isoformat().replace("+00:00", "Z")
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet)
        self.assertFalse(result["ready"])
        self.assertIn("bar_1m_lag", result["blocking_reasons"])

    def test_snapshot_expired(self) -> None:
        packet = _good_packet()
        decision = _good_decision(packet)
        decision["recorded_utc"] = "2026-09-02T20:00:00Z"
        decision["intent"]["expires_utc"] = "2026-09-02T19:00:00Z"
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet, decision=decision)
        self.assertFalse(result["ready"])
        self.assertIn("snapshot_expired", result["blocking_reasons"])

    def test_insufficient_instrument_capacity(self) -> None:
        packet = _good_packet()
        packet.pop("market_observation")
        packet["market"].pop("last")
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet)
        self.assertFalse(result["ready"])
        self.assertIn("insufficient_instrument_capacity", result["blocking_reasons"])

    def test_evidence_chain_incomplete(self) -> None:
        packet = _good_packet()
        result = mod.evaluation_measurement_ready(mode="capture", packet=packet, decision=None, receipt=None)
        self.assertFalse(result["ready"])
        self.assertIn("evidence_chain_incomplete", result["blocking_reasons"])

    def test_maintenance_window(self) -> None:
        health = _good_health()
        health["recovery"] = {"active": True}
        result = mod.evaluation_measurement_ready(mode="preflight", gateway_health=health)
        self.assertFalse(result["ready"])
        self.assertIn("maintenance_window", result["blocking_reasons"])

    def test_market_not_valid(self) -> None:
        health = _good_health()
        health["data_quality"]["operational"]["marketStream"]["state"] = "disconnected"
        result = mod.evaluation_measurement_ready(mode="preflight", gateway_health=health)
        self.assertFalse(result["ready"])
        self.assertIn("market_not_valid", result["blocking_reasons"])

    def test_preflight_ok_without_packet(self) -> None:
        result = mod.evaluation_measurement_ready(mode="preflight", gateway_health=_good_health())
        self.assertTrue(result["ready"])


if __name__ == "__main__":
    unittest.main()
