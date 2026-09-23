"""Tests for offline paper simulator."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

_SPEC = importlib.util.spec_from_file_location("paper_simulator", SCRIPTS / "paper_simulator.py")
PAPER = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(PAPER)

AGG = importlib.util.spec_from_file_location("ensemble_aggregator", SCRIPTS / "ensemble_aggregator.py")
AGG_MOD = importlib.util.module_from_spec(AGG)
assert AGG and AGG.loader
AGG.loader.exec_module(AGG_MOD)

RULES = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))


def _envelope(**overrides: object) -> dict:
    now = datetime.now(timezone.utc)
    base = {
        "envelope_id": "env-paper-test",
        "instrument": "MNQ",
        "snapshot_hash": "a" * 64,
        "envelope_hash": "a" * 64,
        "reference_utc": now.isoformat().replace("+00:00", "Z"),
        "valid_until_utc": (now + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        "contract": {"tick_size": 0.25, "tick_value": 0.5},
        "packet": {
            "market": {"last": 100.0},
            "contract": {"tick_size": 0.25, "tick_value": 0.5},
        },
    }
    base.update(overrides)
    return base


def _profile(
    profile_id: str,
    *,
    state: str = "candidate",
    direction: str = "long",
    entry: float = 100.0,
    stop: float = 99.0,
    target: float = 102.0,
    evidence_score: int = 40,
) -> dict:
    return {
        "profile_id": profile_id,
        "state": state,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "horizon_bars": 8,
        "evidence_score": evidence_score,
        "envelope_hash": "a" * 64,
    }


class PaperSimulatorTests(unittest.TestCase):
    def test_no_selection(self) -> None:
        profiles = [
            _profile("baseline-current", state="no_edge", direction="flat"),
            _profile("structure", state="no_edge", direction="flat"),
        ]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=[{"high": 101.0, "low": 99.5, "close": 100.5}],
            rules=RULES,
            run_id="no-selection",
        )
        self.assertEqual(result["paper_status"], "paper_no_selection")
        self.assertTrue(result["paper_only"])
        self.assertFalse(result["promotion_use_allowed"])
        self.assertEqual(result["operational_writes"], 0)

    def test_selected_candidate_target_before_stop(self) -> None:
        profiles = [
            _profile("baseline-current", evidence_score=50),
            _profile("structure", evidence_score=30),
        ]
        chronology = [{"high": 103.0, "low": 99.5, "close": 102.0}]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="target-first",
        )
        self.assertEqual(result["paper_status"], "paper_outcome")
        path = result["trade_path"]
        self.assertEqual(path["first_touch"], "target")
        self.assertEqual(path["exit_cause"], "target")
        self.assertGreater(path["pnl_ticks"], 0)

    def test_opposite_candidates_aggregator_resolves(self) -> None:
        profiles = [
            _profile("baseline-current", direction="long"),
            _profile("structure", direction="short", stop=101.0, target=98.0),
        ]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=[{"high": 101.0, "low": 99.0, "close": 100.0}],
            rules=RULES,
            run_id="opposite",
        )
        self.assertEqual(result["paper_status"], "paper_no_selection")
        self.assertEqual(result["selection"]["decision_code"], "DIRECTION_CONFLICT")

    def test_stop_before_target(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        chronology = [{"high": 100.5, "low": 98.5, "close": 99.0}]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="stop-first",
        )
        self.assertEqual(result["paper_status"], "paper_outcome")
        self.assertEqual(result["trade_path"]["first_touch"], "stop")
        self.assertLess(result["trade_path"]["pnl_ticks"], 0)

    def test_target_before_stop_separate_bars(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        chronology = [
            {"high": 101.5, "low": 99.5, "close": 101.0},
            {"high": 103.0, "low": 100.5, "close": 102.5},
        ]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="target-bar1",
        )
        self.assertEqual(result["trade_path"]["first_touch"], "target")

    def test_missing_intra_bar_evidence(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        chronology = [{"high": 103.0, "low": 98.0, "close": 100.0}]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="ambiguous",
        )
        self.assertEqual(result["paper_status"], "paper_selected")
        self.assertTrue(result["trade_path"]["intra_bar_evidence_missing"])
        self.assertEqual(result["trade_path"]["first_touch"], "ambiguous")

    def test_incomplete_data(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=None,
            rules=RULES,
            run_id="incomplete",
        )
        self.assertEqual(result["paper_status"], "paper_rejected")
        self.assertEqual(result["rejection_reason"], "incomplete_chronology")

    def test_expired_snapshot(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        envelope = _envelope(
            reference_utc=past.isoformat().replace("+00:00", "Z"),
            valid_until_utc=(past + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        )
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = PAPER.simulate_paper(
            envelope=envelope,
            profile_outputs=profiles,
            chronology=[{"high": 101.0, "low": 99.0, "close": 100.0}],
            rules=RULES,
            run_id="expired",
        )
        self.assertEqual(result["paper_status"], "paper_expired")

    def test_multiple_profiles_input(self) -> None:
        profiles = [
            _profile("baseline-current"),
            _profile("structure", evidence_score=30),
            _profile("orderflow", evidence_score=25),
            _profile("indicators", state="no_edge", direction="flat"),
            _profile("smart-money", state="no_edge", direction="flat"),
            _profile("adversarial-risk", state="no_edge", direction="flat"),
        ]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=[{"high": 102.5, "low": 99.5, "close": 101.0}],
            rules=RULES,
            run_id="six-profile",
        )
        self.assertIn(result["paper_status"], {"paper_outcome", "paper_no_selection", "paper_selected"})
        self.assertGreaterEqual(len(result["selection"]["candidates_considered"]), 2)

    def test_determinism_same_input_same_output(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        chronology = [{"high": 102.0, "low": 99.5, "close": 101.0}]
        envelope = _envelope()
        a = PAPER.simulate_paper(
            envelope=envelope,
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="determinism",
        )
        b = PAPER.simulate_paper(
            envelope=envelope,
            profile_outputs=profiles,
            chronology=chronology,
            rules=RULES,
            run_id="determinism",
        )
        self.assertEqual(a["paper_status"], b["paper_status"])
        self.assertEqual(a["selection"]["decision_code"], b["selection"]["decision_code"])
        if a.get("trade_path") and b.get("trade_path"):
            self.assertEqual(a["trade_path"]["first_touch"], b["trade_path"]["first_touch"])

    def test_zero_writes_operational_snapshot_unchanged(self) -> None:
        snapshot = {"lifecycle": {"state": "ready"}, "writes": 0, "nested": {"a": 1}}
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = PAPER.simulate_paper(
            envelope=_envelope(),
            profile_outputs=profiles,
            chronology=[{"high": 102.0, "low": 99.5, "close": 101.0}],
            rules=RULES,
            run_id="zero-writes",
            operational_snapshot=snapshot,
        )
        self.assertEqual(result["operational_writes"], 0)
        self.assertTrue(result["operational_snapshot_unchanged"])
        self.assertEqual(snapshot, {"lifecycle": {"state": "ready"}, "writes": 0, "nested": {"a": 1}})

    def test_isolation_no_forbidden_imports(self) -> None:
        PAPER.assert_paper_simulator_isolation()

    def test_forward_observation_from_frame(self) -> None:
        frame = json.loads(
            (FIXTURES / "frozen_corpus" / "minute-frames" / "20260820T1201Z.json").read_text(encoding="utf-8")
        )
        profiles = [
            {
                "profile_id": "baseline-current",
                "state": "candidate",
                "direction": "long",
                "entry": 20020.0,
                "stop": 20010.0,
                "target": 20035.0,
                "horizon_bars": 8,
                "evidence_score": 50,
                "envelope_hash": "a" * 64,
            },
            {
                "profile_id": "structure",
                "state": "candidate",
                "direction": "long",
                "entry": 20020.0,
                "stop": 20010.0,
                "target": 20035.0,
                "horizon_bars": 8,
                "evidence_score": 30,
                "envelope_hash": "a" * 64,
            },
        ]
        envelope = _envelope(
            packet=frame["packet"],
            envelope_hash="a" * 64,
            snapshot_hash="a" * 64,
        )
        result = PAPER.simulate_paper(
            envelope=envelope,
            profile_outputs=profiles,
            frame=frame,
            rules=RULES,
            run_id="fixture-frame",
        )
        self.assertEqual(result["paper_status"], "paper_outcome")
        self.assertEqual(result["trade_path"]["first_touch"], "target")


if __name__ == "__main__":
    unittest.main()
