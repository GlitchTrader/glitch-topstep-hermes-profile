"""Tests for evaluation output contract adapter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluation_output_adapter import adapt_evaluation_output, classify_raw_output, load_output_contract

COMPARABLE_GATE = {"comparable": True, "missing_required": [], "stale_or_inconsistent": []}
NOT_COMPARABLE_GATE = {"comparable": False, "missing_required": [], "stale_or_inconsistent": []}
MISSING_GATE = {"comparable": False, "missing_required": ["ohlc"], "stale_or_inconsistent": []}
STALE_GATE = {"comparable": False, "missing_required": [], "stale_or_inconsistent": ["ohlc"]}

VALID_CANDIDATE = {
    "state": "candidate",
    "direction": "long",
    "thesis": "Breakout.",
    "entry": 100.0,
    "stop": 99.0,
    "target": 102.0,
}


class EvaluationOutputAdapterTests(unittest.TestCase):
  # --- unknown / invalid vocabulary ---

    def test_unknown_state_maps_to_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "WATCHING", "direction": "flat", "thesis": "Unclear."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "unapproved_vocabulary")

    def test_state_object_is_contract_violation(self) -> None:
        classification = classify_raw_output({"state": {"instrument": "MNQ"}, "direction": "FLAT"})
        self.assertEqual(classification["category"], "contract_violation")
        adapted = adapt_evaluation_output(
            raw={"state": {"instrument": "MNQ"}, "direction": "FLAT", "thesis": "x"},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "state_field_contains_snapshot")

    def test_state_array_is_parsing_error(self) -> None:
        classification = classify_raw_output({"state": ["candidate"], "direction": "long", "thesis": "x"})
        self.assertEqual(classification["category"], "parsing_error")
        adapted = adapt_evaluation_output(
            raw={"state": ["candidate"], "direction": "long", "thesis": "x"},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "state_field_is_array")

    def test_missing_state_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"direction": "flat", "thesis": "Waiting."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "missing_state")

    def test_missing_thesis_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "flat", "thesis": ""},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "missing_thesis")

    def test_action_nothing_without_state_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"action": "NOTHING", "direction": "flat", "thesis": "Nothing."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertIn(adapted["error_code"], {"action_without_canonical_state", "missing_state"})

  # --- approved state aliases ---

    def test_approved_state_alias_no_edge(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "NO_EDGE", "direction": "flat", "thesis": "No setup."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "no_edge")

    def test_approved_state_alias_candidate(self) -> None:
        adapted = adapt_evaluation_output(
            raw={**VALID_CANDIDATE, "state": "CANDIDATE"},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "candidate")

    def test_approved_state_alias_held(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "HELD",
                "direction": "short",
                "thesis": "Managing.",
                "entry": 100.0,
                "stop": 101.0,
                "target_absence_reason": "trail",
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "held")
        self.assertEqual(adapted["direction"], "short")

    def test_approved_state_alias_hold_maps_to_held(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "HOLD",
                "direction": "long",
                "thesis": "Managing.",
                "entry": 100.0,
                "stop": 99.0,
                "target_absence_reason": "trail",
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "held")

    def test_approved_state_alias_data_degraded(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "DATA_DEGRADED", "direction": "flat", "thesis": "Thin data."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "data_quality_insufficient")

    def test_approved_state_alias_degraded(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "DEGRADED", "direction": "hold", "thesis": "Thin data."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "data_quality_insufficient")

    def test_approved_state_alias_expired(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "EXPIRED", "direction": "flat", "thesis": "Stale."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "expired")

    def test_approved_state_alias_timeout(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "TIMEOUT", "direction": "flat", "thesis": "Timed out."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "timeout")

    def test_approved_state_alias_error(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "ERROR", "direction": "flat", "thesis": "Failed."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "error")

  # --- approved direction aliases ---

    def test_approved_direction_alias_maps(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "FLAT", "thesis": "No setup."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["direction"], "flat")

    def test_approved_direction_alias_long(self) -> None:
        adapted = adapt_evaluation_output(
            raw={**VALID_CANDIDATE, "direction": "LONG"},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["direction"], "long")

    def test_approved_direction_alias_short(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "SHORT",
                "thesis": "Fade.",
                "entry": 100.0,
                "stop": 101.0,
                "target": 98.0,
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["direction"], "short")

    def test_approved_direction_alias_hold(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "HOLD", "thesis": "Waiting."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["direction"], "hold")

  # --- ambiguous vocabulary ---

    def test_bearish_direction_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "BEARISH", "thesis": "Bias down."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "ambiguous_direction_vocabulary")

    def test_bullish_direction_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "BULLISH", "thesis": "Bias up."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "ambiguous_direction_vocabulary")

    def test_neutral_direction_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "NEUTRAL", "thesis": "No bias."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")

    def test_frozen_state_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "frozen", "direction": "flat", "thesis": "Paused."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "ambiguous_state_vocabulary")

    def test_active_state_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "active", "direction": "flat", "thesis": "Running."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")

    def test_idle_state_is_ambiguous(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "idle", "direction": "flat", "thesis": "Idle."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")

  # --- geometry / directional rules ---

    def test_no_silent_flat_to_no_edge_from_direction_only(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"direction": "FLAT", "thesis": "Waiting."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")

    def test_candidate_without_geometry_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "candidate", "direction": "long", "thesis": "Breakout."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "directional_without_geometry")

    def test_candidate_flat_without_geometry_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "flat",
                "thesis": "Resistance level without setup.",
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "candidate_direction_flat_conflict")

    def test_incomplete_directional_candidate_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "long",
                "thesis": "Breakout.",
                "entry": 100.0,
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "directional_without_geometry")

    def test_candidate_with_entry_range_geometry(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "long",
                "thesis": "Zone entry.",
                "entry_range": {"low": 99.5, "high": 100.5},
                "stop": 99.0,
                "target": 102.0,
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "candidate")
        self.assertEqual(adapted["direction"], "long")

    def test_candidate_hold_direction_is_invalid(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "hold",
                "thesis": "Invalid combo.",
                "entry": 100.0,
                "stop": 99.0,
                "target": 102.0,
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "invalid")
        self.assertEqual(adapted["error_code"], "candidate_direction_flat_conflict")

    def test_valid_candidate_with_geometry(self) -> None:
        adapted = adapt_evaluation_output(
            raw=VALID_CANDIDATE,
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "candidate")
        self.assertEqual(adapted["direction"], "long")

    def test_direction_preserved_on_valid_candidate(self) -> None:
        adapted = adapt_evaluation_output(
            raw={
                "state": "candidate",
                "direction": "short",
                "thesis": "Fade.",
                "entry": 100.0,
                "stop": 101.0,
                "target": 98.0,
            },
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["direction"], "short")
        self.assertEqual(adapted["profile_declared_direction"], "short")

  # --- abstention / no_edge ---

    def test_no_edge_flat_is_valid_abstention(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "flat", "thesis": "Low volatility, no momentum."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "no_edge")
        self.assertEqual(adapted["direction"], "flat")
        self.assertIsNone(adapted["error_code"])

    def test_valid_no_edge_not_corrected_to_candidate(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "hold", "thesis": "Waiting for structure."},
            gate=COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "no_edge")
        self.assertNotEqual(adapted["state"], "candidate")
        self.assertIsNone(adapted["error_code"])

  # --- capacity gate overlays ---

    def test_missing_required_gate_unchanged(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "flat", "thesis": "x"},
            gate=MISSING_GATE,
        )
        self.assertEqual(adapted["state"], "missing_required_evidence")
        self.assertEqual(adapted["comparability"], "not_comparable")
        self.assertEqual(adapted["capacity_gate_reason"], "missing_required")

    def test_stale_or_inconsistent_gate(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "flat", "thesis": "x"},
            gate=STALE_GATE,
        )
        self.assertEqual(adapted["state"], "missing_required_evidence")
        self.assertEqual(adapted["capacity_gate_reason"], "stale_or_inconsistent")

    def test_semantically_valid_but_not_comparable_via_gate(self) -> None:
        adapted = adapt_evaluation_output(
            raw={"state": "no_edge", "direction": "flat", "thesis": "Thin evidence."},
            gate=NOT_COMPARABLE_GATE,
        )
        self.assertEqual(adapted["state"], "no_edge")
        self.assertEqual(adapted["comparability"], "not_comparable")

    def test_profile_declared_fields_preserve_raw(self) -> None:
        raw = {"state": "NO_EDGE", "direction": "FLAT", "thesis": "No setup."}
        adapted = adapt_evaluation_output(raw=raw, gate=COMPARABLE_GATE)
        self.assertEqual(adapted["profile_declared_state"], "NO_EDGE")
        self.assertEqual(adapted["profile_declared_direction"], "FLAT")
        self.assertEqual(adapted["state"], "no_edge")
        self.assertEqual(adapted["direction"], "flat")

  # --- all canonical states reachable ---

    def test_all_canonical_states_in_contract(self) -> None:
        contract = load_output_contract()
        canonical = set(contract["canonical_state_enum"])
        expected = {
            "candidate",
            "held",
            "no_edge",
            "data_quality_insufficient",
            "expired",
            "timeout",
            "error",
        }
        self.assertEqual(canonical, expected)


if __name__ == "__main__":
    unittest.main()
