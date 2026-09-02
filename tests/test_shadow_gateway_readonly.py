"""Tests for shadow gateway read-only mode and explicit shadow modes."""

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


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GW = _load("shadow_gateway_readonly", "shadow_gateway_readonly.py")
SHADOW = _load("shadow_observe_live", "shadow-observe-live.py")
MODES = _load("shadow_modes", "shadow_modes.py")


def _good_health() -> dict:
    return {"status": "ok", "lifecycle": {"state": "ready"}, "data_quality": {"state_complete": True}}


def _good_packet() -> dict:
    now = datetime.now(timezone.utc)
    ts = now.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": "pkt-gw-1",
        "created_utc": ts,
        "instrument": "MNQ",
        "market": {
            "last": 20000.0,
            "bid": 19999.0,
            "ask": 20001.0,
            "quote_valid": True,
            "quote_timestamp": ts,
        },
        "account": {"name": "PRAC", "instrument_open_contracts": 0},
        "contract": {
            "id": "CON.MNQ.202609",
            "name": "MNQ",
            "symbol_id": "MNQ",
            "tick_size": 0.25,
            "tick_value": 0.5,
            "active_contract": True,
        },
        "policy": {"account_stage": "PRAC"},
        "data_quality": {"state_complete": True, "quote_age_ms": 1000},
        "execution": {"daily_capture_locked": False},
    }


class ShadowGatewayReadonlyTests(unittest.TestCase):
    def _mock_get(self, health: dict, packet: dict, *, health_status: int = 200, packet_status: int = 200):
        def getter(path: str, token: str, timeout: float):
            if path == "/health":
                return health_status, health
            if path == "/packet":
                return packet_status, packet
            return 404, {}
        return getter

    def test_gateway_unavailable(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=lambda *_: (503, {}),
            )
        self.assertEqual(ctx.exception.code, "gateway_unavailable")

    def test_maintenance_window(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        health = _good_health()
        health["status"] = "degraded"
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=self._mock_get(health, _good_packet()),
            )
        self.assertEqual(ctx.exception.code, "maintenance_window")

    def test_daily_capture_locked(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        packet = _good_packet()
        packet["execution"]["daily_capture_locked"] = True
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=self._mock_get(_good_health(), packet),
            )
        self.assertEqual(ctx.exception.code, "daily_capture_locked")

    def test_state_incomplete(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        packet = _good_packet()
        packet["data_quality"]["state_complete"] = False
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=self._mock_get(_good_health(), packet),
            )
        self.assertEqual(ctx.exception.code, "state_incomplete")

    def test_valid_response(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        result = GW.fetch_gateway_readonly_snapshot(
            matrix=matrix,
            mapping=mapping,
            token="t",
            http_get=self._mock_get(_good_health(), _good_packet()),
        )
        self.assertIn("envelope", result)
        self.assertEqual(result["methods_used"], ["GET /health", "GET /packet"])
        self.assertEqual(result["mutations"], [])
        self.assertIn("completeness", result["envelope"])

    def test_snapshot_expired(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        packet = _good_packet()
        packet["data_quality"]["quote_age_ms"] = 999_999
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                budget={"max_snapshot_age_ms": 120_000},
                http_get=self._mock_get(_good_health(), packet),
            )
        self.assertEqual(ctx.exception.code, "snapshot_expired")

    def test_gateway_timeout(self) -> None:
        matrix = __import__("json").loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = __import__("json").loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))

        def slow_get(*_args):
            raise GW.ShadowGatewayError("gateway_timeout", "simulated")

        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=slow_get,
            )
        self.assertEqual(ctx.exception.code, "gateway_timeout")


class ShadowModeSemanticsTests(unittest.TestCase):
    def test_fixture_offline_flags(self) -> None:
        flags = MODES.mode_flags(MODES.MODE_FIXTURE_OFFLINE)
        self.assertTrue(flags["evaluation_offline"])
        self.assertFalse(flags["shadow_live"])
        self.assertFalse(flags["shadow_live_read_only"])

    def test_gateway_read_only_flags(self) -> None:
        flags = MODES.mode_flags(MODES.MODE_GATEWAY_READ_ONLY_LIVE)
        self.assertFalse(flags["evaluation_offline"])
        self.assertFalse(flags["shadow_live"])
        self.assertTrue(flags["shadow_live_read_only"])

    def test_fixture_mode_never_shadow_live(self) -> None:
        session = SHADOW.run_shadow_session(run_id="sem-test", mode=SHADOW.MODE_FIXTURE_OFFLINE)
        self.assertEqual(session["status"], "completed")
        self.assertTrue(session["evaluation_offline"])
        self.assertFalse(session["shadow_live"])
        obs = session["observation"]
        self.assertEqual(obs["mode"], "fixture_offline")
        self.assertIn("package_audit", obs)

    def test_authorize_blocked_for_fixture_mode(self) -> None:
        session = SHADOW.run_shadow_session(
            run_id="sem-test",
            mode=SHADOW.MODE_FIXTURE_OFFLINE,
            authorize=True,
        )
        self.assertEqual(session["reason"], "authorize_not_applicable_for_offline_modes")

    @patch.object(SHADOW, "fetch_gateway_readonly_snapshot")
    @patch.object(SHADOW, "operational_artifact_snapshot", return_value={})
    @patch.object(SHADOW, "_load_preflight")
    def test_gateway_mode_mocked(self, mock_load_preflight, _snap, mock_fetch) -> None:
        preflight_mod = type("M", (), {})()
        preflight_mod.shadow_preflight = lambda **_: {"ready": True, "status": "shadow_ready"}
        mock_load_preflight.return_value = preflight_mod
        import json

        config = json.loads((ROOT / "evaluation/shadow-live-run-config.v1.json").read_text(encoding="utf-8"))
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        envelope = SHADOW._seal_frame(SHADOW.DEFAULT_FRAME, config=config, matrix=matrix, mapping=mapping)
        mock_fetch.return_value = {"envelope": envelope}
        session = SHADOW.run_shadow_session(
            run_id="gw-mock",
            mode=SHADOW.MODE_GATEWAY_READ_ONLY_LIVE,
            authorize=True,
        )
        self.assertEqual(session["status"], "completed")
        self.assertTrue(session["shadow_live_read_only"])
        self.assertFalse(session["shadow_live"])
        self.assertFalse(session["evaluation_offline"])

    def test_gateway_mode_without_authorize_blocked(self) -> None:
        session = SHADOW.run_shadow_session(
            run_id="gw-blocked",
            mode=SHADOW.MODE_GATEWAY_READ_ONLY_LIVE,
            authorize=False,
        )
        self.assertEqual(session["status"], "blocked")
        self.assertEqual(session["reason"], "human_authorization_required_for_gateway_read_only_live")


if __name__ == "__main__":
    unittest.main()
