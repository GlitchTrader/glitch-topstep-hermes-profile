"""Tests for coherent read-only evaluation bundle capture."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "coherent_capture"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CAPTURE = _load("capture_coherent_evaluation_bundle", "capture_coherent_evaluation_bundle.py")
MEASUREMENT = _load("evaluation_measurement_ready", "evaluation-measurement-ready.py")
PREFLIGHT = _load("shadow_preflight", "shadow-preflight.py")

MATRIX = json.loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
MAPPING = json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat().replace("+00:00", "Z")


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


def _degraded_health() -> dict:
    health = _good_health()
    health["status"] = "degraded"
    return health


def _good_packet(*, packet_id: str = "pkt-1", partial_bar: bool = False, daily_locked: bool = False) -> dict:
    now = _now()
    bar_utc = (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": packet_id,
        "created_utc": _ts(now),
        "instrument": "MNQ",
        "market": {
            "instrument": "MNQ",
            "last": 20000.0,
            "bid": 19999.0,
            "ask": 20001.0,
            "quote_valid": True,
            "quote_timestamp": _ts(now),
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
        "execution": {"daily_capture_locked": daily_locked},
        "market_observation": {
            "observation": {
                "timeframes": [
                    {
                        "timeframe_minutes": 1,
                        "latest_bar_utc": bar_utc,
                        "latest_bar_partial": partial_bar,
                    }
                ]
            }
        },
    }


def _build_envelope(packet: dict) -> dict:
    from ensemble_envelope import build_evaluation_envelope
    from ensemble_envelope_seal import sealed_envelope_identity

    env = build_evaluation_envelope(
        packet=packet,
        source_catalog=MATRIX["source_catalog"],
        reference_utc=str(packet.get("created_utc") or ""),
        frame_id=str(packet.get("packet_id") or ""),
        corpus_ref="test",
        mapping=MAPPING,
    )
    identity = sealed_envelope_identity(env)
    env["envelope_hash"] = identity["envelope_hash"]
    return env


def _decision_for(packet: dict, *, packet_id: str | None = None) -> dict:
    pid = packet_id or packet["packet_id"]
    env = _build_envelope(packet if packet_id is None else {**packet, "packet_id": pid, "created_utc": packet["created_utc"]})
    now = _now()
    return {
        "packet_id": pid,
        "recorded_utc": _ts(now),
        "intent": {
            "intent_id": f"intent-{pid}",
            "packet_id": pid,
            "snapshot_hash": env["snapshot_hash"],
            "action": "NOTHING",
            "expires_utc": _ts(now + timedelta(minutes=5)),
        },
    }


def _receipt_for(decision: dict) -> dict:
    return {
        "intent_id": decision["intent"]["intent_id"],
        "packet_id": decision["packet_id"],
        "recorded_utc": decision["recorded_utc"],
        "snapshot_hash": decision["intent"]["snapshot_hash"],
        "result": {"status": "accepted"},
    }


class CoherentCaptureStateMixin:
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_root = Path(self._tmpdir.name) / "state"
        self.state_root.mkdir(parents=True)
        (self.state_root / "receipts").mkdir()
        (self.state_root / "minute-frames").mkdir()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write_decisions(self, *rows: dict) -> None:
        path = self.state_root / "decisions.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def _write_receipt_file(self, packet_id: str, receipt: dict) -> None:
        (self.state_root / "receipts" / f"{packet_id}.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )

    def _write_cycle_empirical(self, *, packet_id: str, phase: str = "delivery_complete") -> None:
        row = {
            "schema_version": "glitch.topstep.cycle_empirical.v1",
            "recorded_utc": _ts(),
            "phase": phase,
            "packet_id": packet_id,
        }
        path = self.state_root / "cycle-empirical.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def _write_minute_frame(self, packet: dict, minute_id: str = "20260903T1200Z") -> Path:
        path = self.state_root / "minute-frames" / f"{minute_id}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "glitch.topstep.minute_frame.v2",
                    "minute_id": minute_id,
                    "packet": packet,
                }
            ),
            encoding="utf-8",
        )
        return path


class CoherentCaptureTests(CoherentCaptureStateMixin, unittest.TestCase):
    def _mock_http(self, health: dict, packet: dict):
        def getter(path: str, token: str, timeout: float):
            if path == "/health":
                return 200, health
            if path == "/packet":
                return 200, packet
            return 404, {}

        return getter

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_complete_coherent_snapshot(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-coherent")
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_LIVE_GATEWAY,
            packet=packet,
            health=_good_health(),
        )
        self.assertTrue(result["ready"])
        self.assertIsNone(result["not_ready_reason"])
        self.assertEqual(result["packet_id"], "pkt-coherent")
        self.assertEqual(result["decision"]["packet_id"], "pkt-coherent")
        self.assertEqual(result["receipt"]["packet_id"], "pkt-coherent")
        self.assertEqual(result["decision"]["intent"]["packet_id"], "pkt-coherent")
        self.assertEqual(result["snapshot_hash"], decision["intent"]["snapshot_hash"])
        self.assertEqual(result["operational_writes"], 0)

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_delivery_complete_valid_bundle(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-delivery-ok")
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        frame_path = self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["capture_mode"], "delivery_complete")
        self.assertIsNotNone(result["anchor"])
        self.assertEqual(result["anchor"]["packet_id"], "pkt-delivery-ok")
        self.assertIn(str(frame_path), result["anchor"]["minute_frame_path"])
        self.assertEqual(result["methods_used"], [])

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_delivery_complete_frozen_chain_same_packet_id(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-chain")
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertEqual(result["packet"]["packet_id"], result["decision"]["packet_id"])
        self.assertEqual(result["packet"]["packet_id"], result["receipt"]["packet_id"])

    def test_live_gateway_new_uuid_not_correlatable(self) -> None:
        live_packet = _good_packet(packet_id="pkt-live-mint")
        profile_packet = _good_packet(packet_id="pkt-profile-bound")
        decision = _decision_for(profile_packet)
        self._write_decisions(decision)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_LIVE_GATEWAY,
            packet=live_packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "live_packet_not_correlatable")

    def test_packet_advances_between_reads(self) -> None:
        pkt_a = _good_packet(packet_id="pkt-a")
        pkt_b = _good_packet(packet_id="pkt-b")
        decision_a = _decision_for(pkt_a)
        self._write_decisions(decision_a)

        first = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=pkt_a,
            health=_good_health(),
        )
        second = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=pkt_b,
            health=_good_health(),
        )
        self.assertEqual(first["packet_id"], "pkt-a")
        self.assertEqual(second["packet_id"], "pkt-b")
        self.assertIn(second["not_ready_reason"], {"packet_advanced_no_match", "decision_not_yet_available_for_packet"})
        self.assertFalse(second["ready"])

    def test_decision_arrives_after_packet(self) -> None:
        packet = _good_packet(packet_id="pkt-wait-decision")
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "decision_not_yet_available_for_packet")

    def test_receipt_after_decision(self) -> None:
        packet = _good_packet(packet_id="pkt-wait-receipt")
        decision = _decision_for(packet)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "receipt_not_yet_available_for_packet")

    def test_current_packet_without_decision(self) -> None:
        packet = _good_packet(packet_id="pkt-empty")
        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "decision_not_yet_available_for_packet")

    def test_old_packet_decision_rejected(self) -> None:
        packet = _good_packet(packet_id="pkt-new")
        old_packet = _good_packet(packet_id="pkt-old")
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(_decision_for(old_packet))
        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "packet_advanced_no_match")

    def test_gateway_unavailable(self) -> None:
        def bad_get(*_args):
            raise CAPTURE.ShadowGatewayError("gateway_unavailable", "simulated")

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            capture_mode=CAPTURE.CAPTURE_MODE_LIVE_GATEWAY,
            http_get=bad_get,
            token="t",
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "gateway_unavailable")

    def test_gateway_timeout(self) -> None:
        def timeout_get(*_args):
            raise CAPTURE.ShadowGatewayError("gateway_timeout", "simulated")

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            capture_mode=CAPTURE.CAPTURE_MODE_LIVE_GATEWAY,
            http_get=timeout_get,
            token="t",
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "gateway_timeout")

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_partial_bar_blocks_ready(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-partial", partial_bar=True)
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "bar_1m_partial")

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_maintenance_window_blocks_ready(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-maint")
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_degraded_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "maintenance_window")

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_daily_capture_locked_blocks_ready(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-dc-lock", daily_locked=True)
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "daily_capture_locked")

    def test_operational_writes_zero(self) -> None:
        packet = _good_packet()
        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertEqual(result["operational_writes"], 0)

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_mixed_cycle_rejected(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-mix")
        decision = _decision_for(packet)
        receipt = _receipt_for(decision)
        receipt["packet_id"] = "pkt-other"
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "packet_id_mismatch_receipt")

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_snapshot_hash_mismatch_rejected(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-hash")
        decision = _decision_for(packet)
        decision["intent"]["snapshot_hash"] = "0" * 64
        receipt = _receipt_for(decision)
        receipt["snapshot_hash"] = "0" * 64
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "snapshot_hash_mismatch_decision")

    @patch.object(MEASUREMENT, "_capacity_ok", return_value=(True, "ok"))
    def test_future_data_rejected(self, _cap: object) -> None:
        packet = _good_packet(packet_id="pkt-future")
        decision = _decision_for(packet)
        decision["recorded_utc"] = _ts(_now() - timedelta(minutes=5))
        receipt = _receipt_for(decision)
        self._write_minute_frame(packet)
        self._write_cycle_empirical(packet_id=packet["packet_id"])
        self._write_decisions(decision)
        self._write_receipt_file(packet["packet_id"], receipt)

        result = CAPTURE.capture_coherent_evaluation_bundle(
            state_root=self.state_root,
            matrix=MATRIX,
            mapping=MAPPING,
            skip_gateway=True,
            capture_mode=CAPTURE.CAPTURE_MODE_DELIVERY_COMPLETE,
            packet=packet,
            health=_good_health(),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["not_ready_reason"], "future_data_rejected")


class CoherentPreflightWireTests(unittest.TestCase):
    @patch.object(PREFLIGHT, "ensure_evaluation_auth_ready", return_value=(True, None))
    def test_preflight_accepts_coherent_bundle(self, _auth) -> None:
        replay_mod = type("M", (), {"preflight_evaluation_replay": staticmethod(lambda **_: {"ok": True})})
        packet = _good_packet(packet_id="pkt-preflight")
        bundle = {
            "schema_version": CAPTURE.BUNDLE_SCHEMA,
            "capture_mode": "delivery_complete",
            "ready": False,
            "not_ready_reason": "decision_not_yet_available_for_packet",
            "packet_id": packet["packet_id"],
            "health": _good_health(),
            "packet": packet,
            "decision": None,
            "receipt": None,
        }
        with patch.object(PREFLIGHT, "_load_replay_preflight", return_value=replay_mod):
            result = PREFLIGHT.shadow_preflight(
                run_id="coherent-wire",
                coherent_bundle=bundle,
            )
        check_ids = [c["id"] for c in result["checks"]]
        self.assertIn("coherent_evaluation_bundle", check_ids)
        self.assertIn("decision_not_yet_available_for_packet", result["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
