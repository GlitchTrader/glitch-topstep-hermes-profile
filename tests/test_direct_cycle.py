import argparse
import copy
import importlib
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
PARITY = importlib.import_module("parity")


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

    def test_evidence_fingerprint_ignores_snapshot_hash(self):
        first = packet(6)
        second = copy.deepcopy(first)
        second["packet_id"] = "packet-6b"
        second["market"]["snapshot_hash"] = "hash-2"
        second["data_quality"]["quote_age_ms"] = 99999
        self.assertEqual(
            MODULE.evidence_fingerprint(first),
            MODULE.evidence_fingerprint(second),
        )

    def test_skip_unchanged_evidence_when_flat(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            current = packet(6)
            MODULE.write_last_evidence_fingerprint(
                state,
                current,
                MODULE.evidence_fingerprint(current),
            )
            with mock.patch.dict(
                os.environ,
                {"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE": "true"},
            ):
                self.assertTrue(
                    MODULE.should_skip_unchanged_evidence(current, None, state)
                )

    def test_never_skip_unchanged_evidence_when_positioned(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            current = packet(6, positioned=True)
            MODULE.write_last_evidence_fingerprint(
                state,
                current,
                MODULE.evidence_fingerprint(current),
            )
            with mock.patch.dict(
                os.environ,
                {"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE": "true"},
            ):
                self.assertFalse(
                    MODULE.should_skip_unchanged_evidence(current, None, state)
                )

    def test_fingerprint_changes_when_price_changes(self):
        first = packet(6)
        second = copy.deepcopy(first)
        second["market"]["last"] = float(second["market"]["last"]) + 1.0
        self.assertNotEqual(
            MODULE.evidence_fingerprint(first),
            MODULE.evidence_fingerprint(second),
        )

    def test_stale_gateway_skip_when_flat_and_incomplete(self):
        current = packet(6, state_complete=False)
        self.assertEqual(
            MODULE.stale_gateway_skip_reason(current, None),
            "incomplete_gateway_state",
        )

    def test_stale_gateway_skip_not_when_positioned(self):
        current = packet(6, state_complete=False, positioned=True)
        self.assertIsNone(MODULE.stale_gateway_skip_reason(current, None))

    def test_stale_gateway_skip_on_quote_age(self):
        current = packet(6)
        current["data_quality"]["quote_age_ms"] = 12000
        self.assertEqual(
            MODULE.stale_gateway_skip_reason(current, None),
            "stale_gateway_quote",
        )

    def test_retry_after_failure_blocks_unchanged_skip(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            attempts = state / "attempts"
            attempts.mkdir(parents=True)
            write_json = MODULE.write_json_atomic
            write_json(
                attempts / "prior.json",
                {
                    "schema_version": "glitch.topstep.model_attempt.v2",
                    "packet_id": "prior",
                    "status": "failed",
                },
            )
            current = packet(6)
            write_json(
                state / "last-evidence.json",
                {
                    "schema_version": "glitch.topstep.last_evidence.v1",
                    "fingerprint": MODULE.evidence_fingerprint(current),
                },
            )
            with mock.patch.dict(
                os.environ,
                {"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE": "true"},
            ):
                self.assertFalse(
                    MODULE.should_skip_unchanged_evidence(
                        current,
                        None,
                        state,
                    )
                )

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

    def test_prepare_intent_for_delivery_truncates_gateway_string_fields(self):
        value = MODULE.normalize_intent(intent(), packet())
        value["reason"] = "r" * 1100
        value["decision_audit"]["bear_case"] = "x" * 600
        value["decision_audit"]["decisive_evidence"] = "y" * 586
        with mock.patch.object(MODULE, "request_json") as request_json:
            request_json.return_value = (200, packet())
            with mock.patch.object(MODULE, "local_token", return_value="test-token"):
                with mock.patch.object(MODULE, "packet_is_current", return_value=True):
                    delivered = MODULE.prepare_intent_for_delivery(value, None)
        self.assertEqual(len(delivered["reason"]), MODULE.GATEWAY_REASON_MAX_LENGTH)
        self.assertEqual(len(delivered["decision_audit"]["bear_case"]), MODULE.GATEWAY_AUDIT_FIELD_MAX_LENGTH)
        self.assertEqual(len(delivered["decision_audit"]["decisive_evidence"]), MODULE.GATEWAY_AUDIT_FIELD_MAX_LENGTH)

    def test_invocation_reason_first_packet_without_last_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            reason = PARITY.invocation_reason(packet(5), state, None, flat_decision_interval_minutes=5)
        self.assertEqual(reason, "first_packet")

    def test_invocation_reason_scheduled_on_cadence(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            MODULE.write_json_atomic(
                state / "last-evidence.json",
                {"schema_version": "glitch.topstep.last_evidence.v1", "fingerprint": "x"},
            )
            reason = PARITY.invocation_reason(packet(5), state, None, flat_decision_interval_minutes=5)
        self.assertEqual(reason, "scheduled")

    def test_wake_trigger_fires_on_price_cross(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            supervisor = state / "supervisor"
            supervisor.mkdir(parents=True)
            frames = state / "minute-frames"
            frames.mkdir(parents=True)
            prior = packet(4)
            prior["market"]["last"] = 19990.0
            MODULE.write_json_atomic(
                frames / "20990101T1404Z.json",
                {"minute_id": "20990101T1404Z", "packet": prior},
            )
            current = packet(5)
            current["market"]["last"] = 20010.0
            MODULE.write_json_atomic(
                PARITY.wake_trigger_path(supervisor),
                {
                    "schema_version": "glitch.topstep.wake_triggers.v1",
                    "triggers": [{"type": "PRICE_CROSS", "direction": "ABOVE", "price": 20000.0}],
                },
            )
            self.assertTrue(PARITY.wake_trigger_fired(state, current))

    def test_classify_delivery_result_transport_uncertain(self):
        self.assertEqual(
            PARITY.classify_delivery_result({"transport_error": "timeout"}),
            "transport_uncertain",
        )
        self.assertEqual(
            PARITY.classify_delivery_result({"http_status": 500, "body": {}}),
            "transport_uncertain",
        )

    def test_classify_delivery_result_terminal_rejection(self):
        self.assertEqual(
            PARITY.classify_delivery_result({"http_status": 422, "body": {"status": "invalid"}}),
            "terminal_rejection",
        )

    def test_apply_cognitive_overlay_replaces_verified_text(self):
        old = "Replace with the current evidence-based decision."
        overlay = {
            "status": "active",
            "operation": "replace",
            "target": "core_prompt",
            "expected_old_text": old,
            "expected_old_sha256": __import__("hashlib").sha256(old.encode()).hexdigest(),
            "replacement_text": "Use bounded evidence only.",
        }
        rendered = PARITY.apply_cognitive_overlay(f"Before. {old} After.", overlay)
        self.assertIn("Use bounded evidence only.", rendered)
        self.assertNotIn(old, rendered)

    def test_packet_for_outbox_id_finds_stored_frame(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            frames = state / "minute-frames"
            frames.mkdir(parents=True)
            stored = packet(5)
            MODULE.write_json_atomic(
                frames / "20990101T1405Z.json",
                {"minute_id": "20990101T1405Z", "packet": stored},
            )
            found = PARITY.packet_for_outbox_id(state, "packet-5")
        self.assertEqual(found, stored)

    def test_prune_delivered_outboxes_removes_with_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            outbox = state / "outbox"
            receipts = state / "receipts"
            outbox.mkdir(parents=True)
            receipts.mkdir(parents=True)
            MODULE.write_json_atomic(outbox / "packet-1.json", intent())
            MODULE.write_json_atomic(
                receipts / "packet-1.json",
                {
                    "schema_version": "glitch.topstep.delivery_receipt.v2",
                    "result": {"http_status": 200, "body": {"executor": "ok"}},
                },
            )
            pruned = PARITY.prune_delivered_outboxes(state)
        self.assertEqual(pruned, 1)
        self.assertFalse((outbox / "packet-1.json").exists())

    def test_pending_outbox_validates_against_stored_packet_not_current(self):
        stored = packet(5)
        stored["account"]["name"] = "TopstepX-50K"
        current = packet(6)
        current["account"]["name"] = "Other-Account"
        current["market"]["snapshot_hash"] = "hash-other"
        pending_intent = intent("NOTHING")

        with tempfile.TemporaryDirectory() as root:
            profile_root = Path(root)
            state = MODULE.state_root(profile_root)
            state.mkdir(parents=True)
            frames = state / "minute-frames"
            outbox = state / "outbox"
            frames.mkdir(parents=True)
            outbox.mkdir(parents=True)
            MODULE.write_json_atomic(
                frames / "20990101T1405Z.json",
                {"minute_id": "20990101T1405Z", "packet": stored},
            )
            MODULE.write_json_atomic(outbox / "packet-5.json", pending_intent)

            args = argparse.Namespace(
                profile="glitch-topstep",
                timeout_seconds=30,
                packet_rollover_wait_seconds=0,
                dry_run=False,
            )
            def fake_request_json(path, token=None):
                if path == "/health":
                    return (200, {"status": "ok"})
                return (200, current)

            with mock.patch.object(MODULE, "local_token", return_value="token"), mock.patch.object(
                PARITY,
                "packet_has_advanced",
                return_value=False,
            ), mock.patch.object(
                MODULE,
                "request_json",
                side_effect=fake_request_json,
            ), mock.patch.object(MODULE, "wait_for_packet_rollover", return_value=current), mock.patch.object(
                MODULE,
                "packet_is_current",
                return_value=True,
            ), mock.patch.object(
                MODULE,
                "prepare_intent_for_delivery",
                side_effect=lambda value, _directive: value,
            ), mock.patch.object(
                MODULE,
                "post_intent",
                return_value={"http_status": 200, "body": {"executor": "ok"}},
            ) as post_intent:
                exit_code = MODULE.run_once(args, profile_root)

        self.assertEqual(exit_code, 0)
        post_intent.assert_called_once()
        self.assertFalse((outbox / "packet-5.json").exists())

    def test_discard_stale_outbox_intent_for_nothing_when_packet_advanced(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            outbox = state / "outbox"
            frames = state / "minute-frames"
            outbox.mkdir(parents=True)
            frames.mkdir(parents=True)
            stored = packet(5)
            MODULE.write_json_atomic(
                frames / "20990101T1405Z.json",
                {"packet": stored},
            )
            outbox_path = outbox / "packet-5.json"
            MODULE.write_json_atomic(outbox_path, intent("NOTHING"))
            with mock.patch.object(PARITY, "packet_has_advanced", return_value=True):
                discarded = PARITY.discard_stale_outbox_intent(
                    state,
                    outbox_path,
                    "packet-5",
                    intent("NOTHING"),
                    token="token",
                )
        self.assertTrue(discarded)
        self.assertFalse(outbox_path.exists())

    def test_packet_has_advanced_uses_inequality_not_ordering(self):
        with mock.patch.object(
            PARITY,
            "request_json",
            return_value=(200, {"packet_id": "packet-10"}),
        ):
            self.assertTrue(PARITY.packet_has_advanced("packet-9", token="token"))


if __name__ == "__main__":
    unittest.main()
