import copy
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
SPEC = importlib.util.spec_from_file_location(
    "topstep_cycle",
    SCRIPTS / "run-topstep-cycle.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def packet(
    minute: int = 5,
    *,
    positioned: bool = False,
    state_complete: bool = True,
) -> dict:
    stamp = (
        datetime(2099, 1, 1, 14, minute, tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": f"packet-{minute}",
        "created_utc": stamp,
        "expires_utc": "2099-01-01T15:00:00Z",
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
            "id": "CON",
            "name": "MNQ U99",
            "description": "Micro Nasdaq",
            "symbol_id": "F.US.MNQ",
            "tick_size": 0.25,
            "tick_value": 0.5,
            "active_contract": True,
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
        "data_quality": {
            "state_complete": state_complete,
            "issues": [] if state_complete else ["market_stream_reconnecting"],
        },
        "policy": {
            "account_stage": "express_funded_standard",
            "authority": "operator_configured",
            "verified_at_utc": None,
            "loss_model": "express_funded_eod",
            "starting_balance": 50000,
            "initial_maximum_loss": 2000,
            "highest_end_of_day_balance": 0,
            "hard_loss_floor_usd": -2000,
            "current_buffer_usd": 3000,
            "max_contracts": 5,
        },
        "execution": {
            "gateway_mode": "shadow",
            "new_exposure_technically_supported": state_complete,
            "maximum_additional_contracts": 2,
            "supported_actions": [
                "ENTER_LONG",
                "ENTER_SHORT",
                "HOLD",
                "EXIT",
                "NOTHING",
            ],
            "authority": "Hermes decides",
        },
        "required_output_template": {
            "schema_version": "glitch.intent.v2",
            "intent_id": "GENERATE_UUID",
            "created_utc": stamp,
            "instrument": "MNQ",
            "account": "TopstepX-50K",
            "operator_profile": "glitch-topstep",
            "action": "HOLD" if positioned else "NOTHING",
            "confidence": 0.5,
            "snapshot_hash": "hash-1",
            "model_version": "CONFIGURED_MODEL",
            "prompt_version": "glitch-topstep-v2",
            "reason": "Replace",
            "decision_audit": {
                field: (
                    "HOLD" if positioned else "NOTHING"
                ) if field == "final_choice" else "Replace"
                for field in MODULE.AUDIT_FIELDS
            },
        },
    }


def intent(action: str = "NOTHING", quantity: int = 1) -> dict:
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
        "prompt_version": "glitch-topstep-v2",
        "reason": "Evidence supports this decision.",
        "decision_audit": {
            field: action if field == "final_choice" else "Evidence"
            for field in MODULE.AUDIT_FIELDS
        },
    }
    if action == "ENTER_LONG":
        value.update(
            quantity=quantity,
            order_type="MARKET",
            stop_loss=19990,
            take_profit_1=20020,
        )
    if action == "ENTER_SHORT":
        value.update(
            quantity=quantity,
            order_type="MARKET",
            stop_loss=20010,
            take_profit_1=19980,
        )
    return value


class DirectCycleTests(unittest.TestCase):
    def test_packet_for_model_strips_provider_ids(self):
        value = MODULE.packet_for_model(packet())
        self.assertNotIn("id", value["account"])
        self.assertNotIn("id", value["contract"])
        self.assertNotIn("symbol_id", value["contract"])

    def test_flat_default_cadence_is_every_minute(self):
        with mock.patch.dict(
            os.environ,
            {"GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES": "1"},
        ):
            self.assertTrue(MODULE.should_invoke(packet(6), None))

    def test_configurable_cadence_is_scheduling_not_eligibility(self):
        with mock.patch.dict(
            os.environ,
            {"GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES": "5"},
        ):
            self.assertTrue(
                MODULE.should_invoke(packet(5, state_complete=False), None)
            )
            self.assertFalse(MODULE.should_invoke(packet(6), None))

    def test_positioned_and_directive_wake_cycle(self):
        self.assertTrue(MODULE.should_invoke(packet(6, positioned=True), None))
        self.assertTrue(MODULE.should_invoke(packet(6), {"status": "pending"}))

    def test_entry_is_not_pre_gated_by_gateway_capacity_metadata(self):
        current_packet = packet(state_complete=False)
        value = MODULE.normalize_intent(intent("ENTER_LONG", 9), current_packet)
        MODULE.validate_intent(value, current_packet)

    def test_positioned_entry_reaches_gateway_for_factual_handling(self):
        current_packet = packet(positioned=True)
        value = MODULE.normalize_intent(intent("ENTER_LONG"), current_packet)
        MODULE.validate_intent(value, current_packet)

    def test_wire_validation_still_rejects_bad_geometry(self):
        current_packet = packet()
        value = MODULE.normalize_intent(intent("ENTER_LONG"), current_packet)
        value["stop_loss"] = 20010
        with self.assertRaisesRegex(ValueError, "long_geometry_invalid"):
            MODULE.validate_intent(value, current_packet)

    def test_prompt_states_agent_authority(self):
        value = MODULE.build_prompt(packet(state_complete=False), [], {}, None)
        self.assertIn("You are the trading operator", value)
        self.assertIn("not an automatic cognitive veto", value)
        self.assertIn("gateway independently verifies", value)

    def test_frame_capture_accepts_first_frame(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            MODULE.capture_frame(packet(1), state)
            self.assertEqual(len(MODULE.recent_frames(state, 5)), 1)

    def test_extract_single_json_accepts_transport_chatter(self):
        raw = "status\n" + json.dumps(intent()) + "\ndone"
        value = MODULE.extract_single_json_object(
            raw,
            schema="glitch.intent.v2",
        )
        self.assertEqual(value["action"], "NOTHING")

    def test_prepare_intent_for_delivery_refreshes_snapshot_hash(self):
        current_packet = packet()
        fresh_packet = copy.deepcopy(current_packet)
        fresh_packet["market"]["snapshot_hash"] = "hash-2"
        with mock.patch.object(
            MODULE,
            "request_json",
            side_effect=[(200, fresh_packet)],
        ), mock.patch.object(MODULE, "local_token", return_value="token"), mock.patch.object(
            MODULE,
            "packet_is_current",
            return_value=True,
        ):
            aligned = MODULE.prepare_intent_for_delivery(intent(), None)
        self.assertEqual(aligned["snapshot_hash"], "hash-2")


if __name__ == "__main__":
    unittest.main()
