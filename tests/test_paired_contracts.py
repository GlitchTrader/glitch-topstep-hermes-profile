"""Paired gateway/profile contract fixtures for PROD-07, CAP-01, MKT-01, ENTRY-01."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "paired"
sys.path.insert(0, str(SCRIPTS))

import compatibility as compatibility_module  # noqa: E402
from packet_model import compact_market_observation_state, packet_for_model  # noqa: E402
from parity import discard_unexecutable_entry_outbox  # noqa: E402


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Prod07PairedCompatibilityTests(unittest.TestCase):
    def test_profile_intersects_live_gateway_health_fixture(self):
        health = _load("gateway_health.json")["health"]
        compatibility_module.verify_gateway_compatibility(health)
        contract = health["compatibility"]
        required = set(compatibility_module.PROFILE_COMPATIBILITY["required_capabilities"])
        advertised = set(contract["capabilities"])
        self.assertTrue(required.issubset(advertised))
        self.assertIn("protected_reduction_saga_v1", required)
        self.assertNotIn("partial_exit_fail_closed_v1", required)
        for name, expected in compatibility_module.PROFILE_COMPATIBILITY[
            "required_semantic_revisions"
        ].items():
            self.assertEqual(contract["semantic_revisions"].get(name), expected)
        for name, expected in compatibility_module.PROFILE_COMPATIBILITY[
            "required_provider_acceptance_evidence"
        ].items():
            self.assertEqual(contract["provider_acceptance_evidence"].get(name), expected)
        self.assertEqual(
            contract["protocol_revision"],
            compatibility_module.PROFILE_COMPATIBILITY["protocol_revision"],
        )
        self.assertEqual(
            contract["semantic_revisions"]["outcome_feed"],
            "glitch.topstep.outcome_feed.v2",
        )


class Cap01DailyCaptureFixtures(unittest.TestCase):
    def test_model_packet_preserves_daily_capture_context_not_as_quota(self):
        packet = _load("cap01_daily_capture_packet.json")
        capture = packet["daily_economics"]["daily_capture"]
        self.assertEqual(capture["schema_version"], "glitch.topstep.daily_capture.v1")
        self.assertEqual(capture["objective_rate_pct"], 0.5)
        self.assertEqual(capture["objective_usd"], 250)
        self.assertEqual(capture["remaining_usd"], 150)
        self.assertIs(capture["reached"], False)
        self.assertTrue(capture["new_exposure_lock_configured"])

        model = packet_for_model(
            packet,
            profile_name="glitch-topstep",
            core_model="test-model",
            prompt_version="glitch-topstep-v2",
        )
        model_capture = model["daily_economics"]["daily_capture"]
        self.assertEqual(model_capture["objective_rate_pct"], 0.5)
        self.assertEqual(model_capture["remaining_usd"], 150)
        # Quantity must come from execution.valid_entry_quantities, never the objective gap.
        self.assertEqual(model["execution"]["valid_entry_quantities"], [1, 2])
        self.assertNotEqual(
            model_capture["remaining_usd"],
            model["execution"]["valid_entry_quantities"][0],
        )

    def test_soul_forbids_quota_and_gap_sizing(self):
        soul = (ROOT / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("daily_economics.daily_capture", soul)
        self.assertIn("0.5%", soul)
        self.assertIn("not a quota", soul)
        self.assertIn("entry trigger", soul)
        self.assertIn("sizing formula", soul)
        self.assertIn("reached=true", soul)


class Mkt01PartialCompletedBarFixtures(unittest.TestCase):
    def test_compact_observation_keeps_distinct_partial_and_completed_roles(self):
        packet = _load("mkt01_partial_completed_bars.json")
        compact = compact_market_observation_state(packet["market_observation"])
        timeframes = compact["observation"]["timeframes"]
        one_m = next(row for row in timeframes if row.get("timeframe_minutes") in (1, "1m"))
        self.assertIsNotNone(one_m["current_partial_bar"])
        self.assertIsNotNone(one_m["prior_completed_bar"])
        self.assertNotEqual(
            one_m["current_partial_bar"]["timestamp"],
            one_m["prior_completed_bar"]["timestamp"],
        )
        self.assertEqual(one_m["partial_progress"], 0.5)
        self.assertEqual(one_m["bar_identity_issues"], [])
        self.assertTrue(one_m["latest_bar_partial"])
        self.assertIn("partial_bar_note", one_m)

    def test_soul_rejects_universal_closed_candle_gate(self):
        soul = (ROOT / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("current_partial_bar", soul)
        self.assertIn("prior_completed_bar", soul)
        self.assertIn("closed candle is not required", soul)
        self.assertIn("Never transfer a fact from one role to the other", soul)


class Entry01BoundedRangeDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "topstep_cycle_paired",
            SCRIPTS / "run-topstep-cycle.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        cls.cycle = module

    def test_in_range_delivery_keeps_frozen_bounds(self):
        fixture = _load("entry01_bounded_range.json")
        intent = fixture["intent_v3_long"]
        packet = fixture["fresh_packet_in_range"]
        with mock.patch.object(
            self.cycle,
            "request_json",
            side_effect=[(200, packet), (200, {"schema_version": "other"})],
        ), mock.patch.object(self.cycle, "validate_intent", return_value=None), mock.patch.object(
            self.cycle,
            "local_token",
            return_value="token",
        ), mock.patch.object(self.cycle, "packet_is_current", return_value=True):
            aligned = self.cycle.prepare_intent_for_delivery(intent, None)
        self.assertEqual(aligned["entry_price_min"], 20990.0)
        self.assertEqual(aligned["entry_price_max"], 21010.0)
        self.assertEqual(aligned["packet_id"], "entry01-packet")

    def test_outside_range_supersedes_once_and_discards_outbox_for_fresh_comparison(self):
        fixture = _load("entry01_bounded_range.json")
        intent = fixture["intent_v3_long"]
        packet = fixture["fresh_packet_outside_range"]
        with mock.patch.object(
            self.cycle,
            "request_json",
            side_effect=[(200, packet), (200, {"schema_version": "other"})],
        ), mock.patch.object(self.cycle, "local_token", return_value="token"), mock.patch.object(
            self.cycle,
            "packet_is_current",
            return_value=True,
        ):
            with self.assertRaises(ValueError) as raised:
                self.cycle.prepare_intent_for_delivery(intent, None)
        self.assertEqual(str(raised.exception), "entry_range_superseded")

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            outbox = state / "outbox.json"
            outbox.write_text("{}", encoding="utf-8")
            discarded = discard_unexecutable_entry_outbox(
                state,
                outbox,
                intent["packet_id"],
                intent,
                raised.exception,
            )
            self.assertTrue(discarded)
            self.assertFalse(outbox.exists())
            # Favorable drift outside the frozen range is not permission to widen.
            self.assertEqual(intent["entry_price_max"], 21010.0)
            self.assertGreater(packet["market"]["ask"], intent["entry_price_max"])


if __name__ == "__main__":
    unittest.main()
