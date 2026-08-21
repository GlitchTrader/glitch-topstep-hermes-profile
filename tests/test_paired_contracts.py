"""Paired gateway/profile contract fixtures for PROD-07, CAP-01, MKT-01, ENTRY-01, EXEC-01, MULTI-01."""

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

import common as common_module  # noqa: E402
import compatibility as compatibility_module  # noqa: E402
from packet_model import compact_market_observation_state, packet_for_model  # noqa: E402
from parity import discard_unexecutable_entry_outbox  # noqa: E402
from scanner_contract import comparison_template, validate_comparison_ledger, MARKER  # noqa: E402


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


class DistributedContractTests(unittest.TestCase):
    def test_paired_contract_publishes_distributed_state_machine(self):
        contract = json.loads((ROOT / "paired-contract.json").read_text(encoding="utf-8"))
        distributed = contract["distributed_contract"]
        self.assertEqual(
            distributed["schema_version"],
            "glitch.topstep.distributed_state_machine.v1",
        )
        self.assertEqual(distributed["cadence"]["flat_decision_interval_minutes"], 5)
        self.assertEqual(
            distributed["amendment_source_schema"],
            "glitch.topstep.amendment_source.v1",
        )

    def test_wave8_skill_files_exist(self):
        for name in ("topstep-setup-state", "topstep-position-management"):
            path = ROOT / "skills" / name / "SKILL.md"
            self.assertTrue(path.is_file(), path)


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


class Exec01ExecutionFactsFixtures(unittest.TestCase):
    def test_execution_facts_page_has_stable_identity_and_live_status(self):
        page = _load("exec01_execution_facts_page.json")
        self.assertEqual(page["schema_version"], "glitch.topstep.execution_facts.v1")
        self.assertGreaterEqual(page["high_water_sequence"], page["count"])
        for fact in page["facts"]:
            self.assertRegex(fact["fact_id"], r"^fact:[^:]+:[a-z_]+$")
            self.assertEqual(fact["status"], "live")
            self.assertEqual(fact["revision"], 1)
            self.assertIsInstance(fact.get("diagnostics"), dict)

    def test_sync_gateway_execution_facts_appends_without_duplicates(self):
        page = _load("exec01_execution_facts_page.json")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with mock.patch.dict(
                "os.environ",
                {"GLITCH_TOPSTEP_LOCAL_TOKEN": "01234567890123456789012345678901"},
                clear=False,
            ), mock.patch.object(
                common_module,
                "request_json",
                return_value=(200, page),
            ):
                first = common_module.sync_gateway_execution_facts(state)
                second = common_module.sync_gateway_execution_facts(state)
            self.assertEqual(first["added"], 3)
            self.assertEqual(first["http_status"], 200)
            self.assertEqual(second["added"], 0)
            self.assertEqual(second["sequence"], 3)
            lines = (state / "execution-facts.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)


class Multi01ScannerPacketFixtures(unittest.TestCase):
    def _packet(self) -> dict:
        universe = _load("multi01_scanner_packet.json")
        return {
            "packet_id": "multi01-packet",
            "expires_utc": "2026-08-20T12:05:00Z",
            "instrument": "MNQ",
            "market_universe": universe,
            "account_selection": universe["account_selection"],
        }

    def test_scanner_universe_preserves_exact_contracts_and_single_armed_selection(self):
        universe = _load("multi01_scanner_packet.json")
        selected = [row for row in universe["candidates"] if row["execution_mode"] == "selected"]
        observation = [row for row in universe["candidates"] if row["execution_mode"] == "observation_only"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["instrument"], "MNQ")
        self.assertEqual(len(observation), 2)
        self.assertFalse(universe["simultaneous_exposure_enabled"])
        self.assertEqual(universe["account_selection"]["selected_contract_id"], "CON.F.US.MNQ.U26")

    def test_scanner_comparison_ledger_requires_all_three_candidates(self):
        packet = self._packet()
        ledger_text = (
            ROOT / "tests" / "fixtures" / "paired" / "multi01_comparison_ledger.txt"
        ).read_text(encoding="utf-8")
        validated = validate_comparison_ledger(ledger_text, packet, action="NOTHING")
        self.assertEqual(validated["ranking"], ["MNQ", "MES", "MCL"])


if __name__ == "__main__":
    unittest.main()
