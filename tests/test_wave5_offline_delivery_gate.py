"""Wave 5 offline delivery gate — selection + revalidation without execution."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(SCRIPTS))

_SPEC = importlib.util.spec_from_file_location("wave5_offline_delivery_gate", SCRIPTS / "wave5_offline_delivery_gate.py")
W5 = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(W5)

_PAPER = importlib.util.spec_from_file_location("paper_simulator", SCRIPTS / "paper_simulator.py")
PAPER = importlib.util.module_from_spec(_PAPER)
assert _PAPER and _PAPER.loader
_PAPER.loader.exec_module(PAPER)

RULES = json.loads((EVAL / "aggregator_rules.v1.json").read_text(encoding="utf-8"))


def _envelope(**overrides: object) -> dict:
    now = datetime.now(timezone.utc)
    base = {
        "envelope_id": "env-w5",
        "instrument": "MNQ",
        "envelope_hash": "a" * 64,
        "snapshot_hash": "a" * 64,
        "reference_utc": now.isoformat().replace("+00:00", "Z"),
        "valid_until_utc": (now + timedelta(seconds=120)).isoformat().replace("+00:00", "Z"),
        "contract": {"generation": "202509", "tick_size": 0.25, "tick_value": 0.5},
    }
    base.update(overrides)
    return base


def _profile(pid: str, **kwargs: object) -> dict:
    return {
        "profile_id": pid,
        "state": kwargs.get("state", "candidate"),
        "direction": kwargs.get("direction", "long"),
        "entry": kwargs.get("entry", 20000.0),
        "stop": kwargs.get("stop", 19990.0),
        "target": kwargs.get("target", 20020.0),
        "horizon_bars": 8,
        "evidence_score": kwargs.get("evidence_score", 50),
        "envelope_hash": "a" * 64,
    }


def _delivery_ok(**overrides: object) -> dict:
    base = {
        "instrument": "MNQ",
        "contract_generation": "202509",
        "quote_age_ms": 1000,
        "max_quote_age_ms": 120_000,
        "daily_capture_locked": False,
        "hard_loss_floor_usd": -2000,
        "account_pnl_usd": 0,
        "geometry_valid": True,
        "allowed_instruments": ["MNQ", "MES", "MCL"],
    }
    base.update(overrides)
    return base


class Wave5OfflineDeliveryGateTests(unittest.TestCase):
    def test_six_profiles_one_global_selection(self) -> None:
        profiles = [
            _profile("baseline-current", evidence_score=55),
            _profile("structure", evidence_score=40),
            _profile("orderflow", evidence_score=35),
            _profile("indicators", evidence_score=30),
            _profile("smart-money", evidence_score=25),
            _profile("adversarial-risk", evidence_score=20),
        ]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(),
            run_id="six-profile",
        )
        self.assertEqual(result["status"], "delivery_ready_offline")
        self.assertEqual(result["intents_emitted"], 0)
        self.assertEqual(result["orders_emitted"], 0)
        self.assertIsNotNone(result["selection"])
        self.assertEqual(result["selection"]["outcome"], "selected")

    def test_no_selection(self) -> None:
        profiles = [_profile("baseline-current", state="no_edge", direction="flat")]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(),
            run_id="no-selection",
        )
        self.assertEqual(result["status"], "no_delivery")
        self.assertEqual(result["intents_emitted"], 0)

    def test_direction_conflict(self) -> None:
        profiles = [
            _profile("baseline-current", direction="long"),
            _profile("structure", direction="short", stop=20010.0, target=19980.0),
        ]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(),
            run_id="conflict",
        )
        self.assertEqual(result["status"], "no_delivery")
        self.assertEqual(result["selection"]["decision_code"], "DIRECTION_CONFLICT")

    def test_missing_profile_still_aggregates(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=30)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(),
            run_id="partial-six",
        )
        self.assertIn(result["status"], {"delivery_ready_offline", "no_delivery"})
        self.assertEqual(result["operational_writes"], 0)

    def test_daily_capture_blocks_delivery(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(daily_capture_locked=True),
            run_id="daily-capture",
        )
        self.assertEqual(result["status"], "delivery_failure")
        self.assertEqual(result["failure_code"], "daily_capture_locked")
        self.assertTrue(result.get("attributable"))

    def test_geometry_invalid_fails_safe(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(geometry_valid=False),
            run_id="geometry",
        )
        self.assertEqual(result["failure_code"], "geometry_invalid")

    def test_invalid_instrument(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(allowed_instruments=["MES", "MCL"]),
            run_id="invalid-instrument",
        )
        self.assertEqual(result["failure_code"], "invalid_instrument")

    def test_contract_expired(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(contract_expired=True),
            run_id="contract-expired",
        )
        self.assertEqual(result["failure_code"], "contract_expired")

    def test_zero_execution_surface(self) -> None:
        profiles = [_profile("baseline-current"), _profile("structure", evidence_score=20)]
        result = W5.run_wave5_offline(
            envelope=_envelope(),
            profile_outputs=profiles,
            rules=RULES,
            delivery_context=_delivery_ok(),
            run_id="zero-exec",
        )
        self.assertEqual(result["projectx_calls"], 0)
        self.assertEqual(result["outbox_writes"], 0)


if __name__ == "__main__":
    unittest.main()
