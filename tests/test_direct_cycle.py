import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("topstep_cycle", SCRIPTS / "run-topstep-cycle.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def packet(minute=5, positioned=False, entry_enabled=True):
    stamp = datetime(2099, 1, 1, 14, minute, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "glitch.direct.decision_packet.v1",
        "packet_id": f"packet-{minute}",
        "created_utc": stamp,
        "venue": "projectx",
        "firm": "topstep",
        "instrument": "MNQ",
        "account": {
            "id": 123,
            "name": "TopstepX-50K",
            "simulated": True,
            "can_trade": True,
            "balance": 1000,
            "unrealized_pnl": 0,
            "conservative_equity": 1000,
            "total_open_contracts": 1 if positioned else 0,
            "instrument_open_contracts": 1 if positioned else 0,
            "working_orders": 2 if positioned else 0,
        },
        "contract": {
            "id": "CON.F.US.MNQ.U99",
            "name": "MNQ U99",
            "symbol_id": "F.US.MNQ",
            "tick_size": 0.25,
            "tick_value": 0.5,
        },
        "market": {
            "snapshot_hash": "hash-1",
            "quote_timestamp": stamp,
            "last": 20000,
            "bid": 19999.75,
            "ask": 20000.25,
            "spread_ticks": 2,
            "session_open": 19950,
            "session_high": 20020,
            "session_low": 19920,
            "volume": 1000,
        },
        "policy": {
            "program": "xfa",
            "account_size": 50000,
            "initial_max_loss": 2000,
            "highest_end_of_day_balance": 1000,
            "liquidation_floor": 0,
            "current_buffer": 1000,
            "allowed_risk_usd": 50,
            "max_contracts": 5,
            "entry_window_open": True,
        },
        "execution": {
            "state_complete": True,
            "entry_actions_enabled": entry_enabled,
            "valid_entry_quantities": [1, 2] if entry_enabled else [],
            "authority": "Glitch validates and executes; Hermes proposes only",
        },
        "required_output_template": {
            "schema_version": "glitch.intent.v2",
            "intent_id": "GENERATE_UUID",
            "created_utc": stamp,
            "instrument": "MNQ",
            "account": "TopstepX-50K",
            "operator_profile": "glitch-toptrader",
            "action": "HOLD" if positioned else "NOTHING",
            "confidence": 0.5,
            "snapshot_hash": "hash-1",
            "model_version": "CONFIGURED_MODEL",
            "prompt_version": "glitch-toptrader-v1",
            "reason": "Replace",
            "decision_audit": {field: ("HOLD" if positioned else "NOTHING") if field == "final_choice" else "Replace" for field in MODULE.AUDIT_FIELDS},
        },
    }


def intent(action="NOTHING"):
    value = {
        "schema_version": "glitch.intent.v2",
        "intent_id": "00000000-0000-4000-8000-000000000001",
        "created_utc": "2099-01-01T14:05:01Z",
        "instrument": "MNQ",
        "account": "TopstepX-50K",
        "operator_profile": "glitch-topstep",
        "action": action,
        "confidence": 0.6,
        "snapshot_hash": "hash-1",
        "model_version": "gpt-5.6-luna",
        "prompt_version": "glitch-topstep-v1",
        "reason": "Evidence supports this bounded decision.",
        "decision_audit": {field: action if field == "final_choice" else "Evidence" for field in MODULE.AUDIT_FIELDS},
    }
    if action == "ENTER_LONG":
        value.update(quantity=1, order_type="MARKET", stop_loss=19990, take_profit_1=20020)
    if action == "ENTER_SHORT":
        value.update(quantity=1, order_type="MARKET", stop_loss=20010, take_profit_1=19980)
    return value


class DirectCycleTests(unittest.TestCase):
    def test_packet_for_model_strips_provider_ids_and_repairs_profile(self):
        value = MODULE.packet_for_model(packet())
        self.assertNotIn("id", value["account"])
        self.assertNotIn("id", value["contract"])
        self.assertNotIn("symbol_id", value["contract"])
        self.assertEqual(value["required_output_template"]["operator_profile"], "glitch-topstep")
        self.assertEqual(value["required_output_template"]["prompt_version"], "glitch-topstep-v2")

    def test_flat_cadence_is_five_minute_boundary(self):
        self.assertTrue(MODULE.should_invoke(packet(5), None))
        self.assertFalse(MODULE.should_invoke(packet(6), None))

    def test_positioned_cadence_is_every_minute(self):
        self.assertTrue(MODULE.should_invoke(packet(6, positioned=True), None))

    def test_directive_wakes_cycle(self):
        self.assertTrue(MODULE.should_invoke(packet(6, entry_enabled=False), {"status": "pending"}))

    def test_flat_ineligible_packet_spends_no_model_call(self):
        self.assertFalse(MODULE.should_invoke(packet(5, entry_enabled=False), None))

    def test_normalize_replaces_legacy_identity_and_uses_deterministic_uuid(self):
        first = MODULE.normalize_intent(intent(), packet())
        second = MODULE.normalize_intent(intent(), packet())
        self.assertEqual(first["operator_profile"], "glitch-topstep")
        self.assertEqual(first["intent_id"], second["intent_id"])
        self.assertEqual(first["snapshot_hash"], "hash-1")

    def test_valid_entry_passes(self):
        value = MODULE.normalize_intent(intent("ENTER_LONG"), packet())
        MODULE.validate_intent(value, packet())

    def test_entry_quantity_must_be_supplied_by_gateway(self):
        value = MODULE.normalize_intent(intent("ENTER_LONG"), packet())
        value["quantity"] = 3
        with self.assertRaisesRegex(ValueError, "entry_quantity_invalid"):
            MODULE.validate_intent(value, packet())

    def test_positioned_entry_fails_closed(self):
        value = MODULE.normalize_intent(intent("ENTER_LONG"), packet(positioned=True))
        with self.assertRaisesRegex(ValueError, "action_not_available"):
            MODULE.validate_intent(value, packet(positioned=True))

    def test_move_stop_requires_tightening(self):
        pkt = packet(positioned=True)
        pkt["execution"] = {"move_stop_available": True, "entry_actions_enabled": False, "valid_entry_quantities": []}
        pkt["position_state"] = {"side": "long", "size": 1}
        pkt["protection"] = {"stop_price": 28900.0}
        value = MODULE.normalize_intent({
            **intent("HOLD"),
            "action": "MOVE_STOP",
            "stop_loss": 28905.0,
            "decision_audit": {field: "MOVE_STOP" if field == "final_choice" else "Replace" for field in MODULE.AUDIT_FIELDS},
        }, pkt)
        MODULE.validate_intent(value, pkt, None)
        with self.assertRaisesRegex(ValueError, "move_stop_must_tighten_long"):
            bad = dict(value)
            bad["stop_loss"] = 28895.0
            MODULE.validate_intent(bad, pkt, None)

    def test_forced_direction_must_be_honored(self):
        value = MODULE.normalize_intent(intent("NOTHING"), packet())
        directive = {"directive_type": "forced_entry", "bias": "long"}
        with self.assertRaisesRegex(ValueError, "forced_entry_not_honored"):
            MODULE.validate_intent(value, packet(), directive)

    def test_extract_single_json_accepts_transport_chatter(self):
        raw = "status line\n" + json.dumps(intent()) + "\ndone"
        self.assertEqual(MODULE.extract_single_json_object(raw, schema="glitch.intent.v2")["action"], "NOTHING")

    def test_extract_single_json_rejects_two_distinct_intents(self):
        with self.assertRaises(json.JSONDecodeError):
            MODULE.extract_single_json_object(json.dumps(intent()) + "\n" + json.dumps(intent("HOLD")), schema="glitch.intent.v2")

    def test_decision_frame_count_reads_env(self):
        with mock.patch.dict(os.environ, {"GLITCH_TOPSTEP_DECISION_FRAME_COUNT": "12"}):
            self.assertEqual(MODULE.decision_frame_count(), 12)

    def test_flat_decision_waits_for_required_frames(self):
        required = 12
        with mock.patch.object(MODULE, "decision_frame_count", return_value=required):
            with tempfile.TemporaryDirectory() as root:
                state = Path(root)
                for minute in range(1, required):
                    MODULE.capture_frame(packet(minute), state)
                frames = MODULE.recent_frames(state)
                self.assertEqual(len(frames), required - 1)
                self.assertLess(len(frames), required)

    def test_frame_capture_is_bounded_and_readable(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with mock.patch.object(MODULE, "frame_retention", return_value=5):
                for minute in range(1, 8):
                    MODULE.capture_frame(packet(minute), state)
            self.assertEqual(len(list((state / "minute-frames").glob("*.json"))), 5)
            self.assertEqual(len(MODULE.recent_frames(state, 5)), 5)

    def test_prompt_forbids_credentials_and_provider_ids(self):
        value = MODULE.build_prompt(packet(), [], {}, None)
        self.assertIn("must never be requested or invented", value)
        envelope = json.loads(value.split("CURRENT_CYCLE=", 1)[1])
        self.assertNotIn("id", envelope["decision_packet"]["account"])
        self.assertEqual(envelope["required_output_template"]["operator_profile"], "glitch-topstep")


if __name__ == "__main__":
    unittest.main()
