"""Tests for explicit quote_state mapping — never no_edge from locked/invalid."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
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


QS = _load("quote_state", "quote_state.py")
GW = _load("shadow_gateway_readonly", "shadow_gateway_readonly.py")
LANE = _load("deferred_data_quality_soak_lane", "deferred_data_quality_soak_lane.py")


LOCKED_EPISODES = [
    {"best_bid": 29423.75, "best_ask": 29423.75},
    {"best_bid": 29456, "best_ask": 29456},
    {"best_bid": 29456, "best_ask": 29456},
    {"best_bid": 29472.25, "best_ask": 29472.25},
    {"best_bid": 29467.75, "best_ask": 29467.75},
    {"best_bid": 29467.75, "best_ask": 29467.75},
]


def _health(issues=None, quote_state=None, state_complete=True, **extra):
    dq = {"state_complete": state_complete, "issues": list(issues or []), **extra}
    if quote_state is not None:
        dq["quote_state"] = quote_state
        dq["data_completeness"] = quote_state in ("normal", "locked")
        dq["execution_eligibility"] = {
            "normal": "eligible",
            "locked": "blocked_locked",
            "invalid": "blocked_invalid",
        }[quote_state]
    return {"status": "ok", "data_quality": dq}


def _packet(issues=None, quote_state=None, state_complete=True, **extra):
    dq = {
        "state_complete": state_complete,
        "issues": list(issues or []),
        "quote_age_ms": 1000,
        **extra,
    }
    if quote_state is not None:
        dq["quote_state"] = quote_state
        dq["data_completeness"] = quote_state in ("normal", "locked")
        dq["execution_eligibility"] = {
            "normal": "eligible",
            "locked": "blocked_locked",
            "invalid": "blocked_invalid",
        }[quote_state]
    return {
        "packet_id": "pkt-qs-1",
        "market": {"bid": 100, "ask": 101, "quote_valid": True},
        "data_quality": dq,
        "execution": {"gateway_mode": "shadow"},
    }


class QuoteStateClassificationTests(unittest.TestCase):
    def test_normal_is_evaluable(self) -> None:
        axes = QS.classify_evaluation_axes(_health(quote_state="normal"), _packet(quote_state="normal"))
        self.assertEqual(axes["quote_state"], "normal")
        self.assertTrue(axes["operational_cycle_valid"])
        self.assertTrue(axes["executable_market_valid"])
        self.assertFalse(axes["directional_opportunity"])
        self.assertFalse(axes["execution_authority"])
        self.assertIsNone(axes["deferred_reason"])
        self.assertTrue(axes["action_matrix"]["new_exposure"])
        self.assertTrue(axes["action_matrix"]["flatten"])

    def test_locked_is_deferred_not_no_edge(self) -> None:
        axes = QS.classify_evaluation_axes(
            _health(issues=["quote_locked"], quote_state="locked", state_complete=False),
            _packet(issues=["quote_locked"], quote_state="locked", state_complete=False),
        )
        self.assertEqual(axes["quote_state"], "locked")
        self.assertTrue(axes["operational_cycle_valid"])
        self.assertFalse(axes["executable_market_valid"])
        self.assertFalse(axes["directional_opportunity"])
        self.assertEqual(axes["deferred_reason"], "no_trade_locked_market")
        self.assertTrue(axes["blocks_no_edge"])
        self.assertFalse(axes["action_matrix"]["new_exposure"])
        self.assertTrue(axes["action_matrix"]["exit_reduction"])
        self.assertTrue(axes["action_matrix"]["flatten"])
        self.assertTrue(axes["action_matrix"]["protective_action"])
        self.assertTrue(axes["action_matrix"]["recovery"])
        self.assertEqual(axes["risk_reduction_eligibility"], "eligible")
        # data_completeness must not authorize execution
        self.assertTrue(axes["data_completeness"])
        self.assertNotEqual(axes["execution_eligibility"], "eligible")

    def test_action_matrix_matches_spec(self) -> None:
        for state, expected in QS.ACTION_MATRIX.items():
            for action, allowed in expected.items():
                eligibility = {
                    "normal": "eligible",
                    "locked": "blocked_locked",
                    "invalid": "blocked_invalid",
                    "stale": "blocked_incomplete",
                }[state]
                self.assertEqual(
                    QS.action_allowed(action, quote_state=state if state != "stale" else "normal", execution_eligibility=eligibility),
                    allowed,
                    f"{state}/{action}",
                )

    def test_invalid_blocks(self) -> None:
        axes = QS.classify_evaluation_axes(
            _health(issues=["quote_geometry_invalid"], quote_state="invalid", state_complete=False),
            _packet(issues=["quote_geometry_invalid"], quote_state="invalid", state_complete=False),
        )
        self.assertEqual(axes["quote_state"], "invalid")
        self.assertFalse(axes["executable_market_valid"])
        self.assertTrue(axes["blocks_no_edge"])

    def test_legacy_issue_codes_without_quote_state_field(self) -> None:
        self.assertEqual(
            QS.resolve_quote_state(
                _health(issues=["quote_locked"], state_complete=False),
                _packet(issues=["quote_locked"], state_complete=False),
            ),
            "locked",
        )
        self.assertEqual(
            QS.resolve_quote_state(
                _health(issues=["quote_geometry_invalid"], state_complete=False),
                _packet(issues=["quote_geometry_invalid"], state_complete=False),
            ),
            "invalid",
        )


class ShadowLockedQuoteTests(unittest.TestCase):
    def _mock_get(self, health, packet):
        def _get(path, _token, _timeout):
            if path == "/health":
                return 200, health
            if path == "/packet":
                return 200, packet
            return 404, {}

        return _get

    def test_locked_raises_deferred_not_evaluable(self) -> None:
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text(encoding="utf-8"))
        mapping = json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
        health = _health(issues=["quote_locked"], quote_state="locked", state_complete=False)
        packet = _packet(issues=["quote_locked"], quote_state="locked", state_complete=False)
        packet["schema_version"] = "glitch.direct.decision_packet.v2"
        packet["created_utc"] = "2026-09-09T16:34:00Z"
        packet["instrument"] = "MNQ"
        packet["account"] = {"name": "PRAC", "instrument_open_contracts": 0}
        with self.assertRaises(GW.ShadowGatewayError) as ctx:
            GW.fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                token="t",
                http_get=self._mock_get(health, packet),
            )
        self.assertEqual(ctx.exception.code, "deferred_data_quality")
        detail = json.loads(ctx.exception.detail)
        self.assertEqual(detail["reason"], "no_trade_locked_market")
        self.assertEqual(detail["quote_state"], "locked")
        self.assertFalse(detail["directional_opportunity"])
        self.assertFalse(detail["executable_market_valid"])

    def test_health_packet_parity_for_locked(self) -> None:
        health = _health(issues=["quote_locked"], quote_state="locked", state_complete=False)
        packet = _packet(issues=["quote_locked"], quote_state="locked", state_complete=False)
        self.assertEqual(QS.resolve_quote_state(health, packet), "locked")
        self.assertEqual(QS.resolve_execution_eligibility(health, packet), "blocked_locked")


class SoakLockedNoFalseT0Tests(unittest.TestCase):
    def test_locked_deferred_never_starts_t0(self) -> None:
        cp = {
            "status": "awaiting_first_valid_cycle",
            "t0_utc": None,
            "completed_cycles": 0,
            "valid_cycles": 0,
            "deferred_cycles": 0,
        }
        for i, episode in enumerate(LOCKED_EPISODES):
            axes = QS.classify_evaluation_axes(
                _health(issues=["quote_locked"], quote_state="locked", state_complete=False),
                _packet(issues=["quote_locked"], quote_state="locked", state_complete=False),
            )
            self.assertEqual(episode["best_bid"], episode["best_ask"])
            self.assertFalse(axes["executable_market_valid"])
            self.assertFalse(axes["directional_opportunity"])
            # Locked is deferred — never VALID_CYCLE / never no_edge.
            updated = LANE.advance_lane_checkpoint(
                cp,
                cycle_id=f"locked-{i}",
                cycle_status=LANE.DEFERRED_DATA_QUALITY,
            )
            self.assertIsNone(updated.get("t0_utc"))
            self.assertEqual(updated["valid_cycles"], 0)
            self.assertEqual(updated["deferred_cycles"], i + 1)
            self.assertNotEqual(updated.get("status"), "no_edge")
            cp = updated


class AggregatorLockedNoEdgeGuardTests(unittest.TestCase):
    def test_locked_never_maps_to_no_edge_label(self) -> None:
        axes = QS.classify_evaluation_axes(
            _health(issues=["quote_locked"], quote_state="locked", state_complete=False),
            _packet(issues=["quote_locked"], quote_state="locked", state_complete=False),
        )
        self.assertNotEqual(axes["deferred_reason"], "no_edge")
        self.assertTrue(axes["blocks_no_edge"])
        self.assertEqual(axes["execution_authority"], False)


if __name__ == "__main__":
    unittest.main()
