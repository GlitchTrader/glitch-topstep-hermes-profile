"""Replay-only proof of instrument selection and identity fail-closed behavior.

These fixtures do not represent live MES/MCL coverage. The ensemble still
receives one instrument per envelope; scanner/ranking/handoff is a separate
upstream concern.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ensemble_aggregator import aggregate_envelope  # noqa: E402
from prac_live_ensemble import RunnerError, validate_live_packet  # noqa: E402

RULES = json.loads((ROOT / "evaluation" / "aggregator_rules.v1.json").read_text(encoding="utf-8"))

INSTRUMENTS = {
    "MNQ": {"contract_id": "CON.F.US.MNQ.U26", "last": 20000.0, "tick_size": 0.25},
    "MES": {"contract_id": "CON.F.US.MES.U26", "last": 5000.0, "tick_size": 0.25},
    "MCL": {"contract_id": "CON.F.US.MCLE.V26", "last": 75.0, "tick_size": 0.01},
}


def envelope_for(instrument: str) -> dict:
    spec = INSTRUMENTS[instrument]
    return {
        "envelope_id": f"env-{instrument.lower()}-replay",
        "instrument": instrument,
        "snapshot_hash": (instrument.lower() * 64)[:64],
        "envelope_hash": (instrument.lower() * 64)[:64],
        "contract": {"id": spec["contract_id"], "tick_size": spec["tick_size"]},
        "packet": {"market": {"last": spec["last"]}, "contract": {"tick_size": spec["tick_size"]}},
    }


def candidate(profile_id: str, instrument: str, score: int) -> dict:
    last = INSTRUMENTS[instrument]["last"]
    distance = 10 * INSTRUMENTS[instrument]["tick_size"]
    return {
        "profile_id": profile_id,
        "invocation_id": f"inv-{profile_id}-{instrument}",
        "state": "candidate",
        "comparability": "comparable",
        "instrument": instrument,
        "quantity": 1,
        "direction": "long",
        "entry": last,
        "stop": last - distance,
        "target": last + (distance * 2),
        "evidence_score": score,
        "thesis": f"Replay evidence for {instrument}.",
        "evidence_refs": [f"fixture:{instrument}:bars"],
        "envelope_hash": envelope_for(instrument)["envelope_hash"],
    }


class MultiMarketSelectionReplayTests(unittest.TestCase):
    def test_winning_selection_is_proven_separately_for_mnq_mes_mcl(self):
        for instrument in INSTRUMENTS:
            with self.subTest(instrument=instrument):
                envelope = envelope_for(instrument)
                result = aggregate_envelope(
                    run_id=f"winner-{instrument}",
                    envelope=envelope,
                    candidates=[candidate("baseline-current", instrument, 20), candidate("structure", instrument, 40)],
                    objections=[],
                    rules=RULES,
                )
                self.assertEqual(result["outcome"], "selected")
                selected = next(
                    row for row in result["candidates_preserved"]
                    if row["profile_id"] == result["selected_profile_id"]
                )
                self.assertEqual(selected["instrument"], instrument)
                self.assertEqual(result["selected_candidate"]["profile_id"], "structure")

    def test_no_silent_fallback_to_mnq_for_mes_or_mcl(self):
        for instrument in ("MES", "MCL"):
            with self.subTest(instrument=instrument):
                envelope = envelope_for(instrument)
                wrong_instrument = candidate("baseline-current", "MNQ", 99)
                wrong_instrument["envelope_hash"] = envelope["envelope_hash"]
                result = aggregate_envelope(
                    run_id=f"no-fallback-{instrument}",
                    envelope=envelope,
                    candidates=[wrong_instrument, candidate("structure", instrument, 10)],
                    objections=[],
                    rules=RULES,
                )
                self.assertEqual(result["outcome"], "no_selection")
                self.assertIsNone(result["selected_profile_id"])
                self.assertIn("OBJECTIVE_ELIMINATION:baseline-current:identity_mismatch", " ".join(result["decision_trace"]))

    def test_missing_or_divergent_instrument_is_fail_closed(self):
        envelope = envelope_for("MES")
        missing = copy.deepcopy(candidate("baseline-current", "MES", 20))
        missing["instrument"] = None
        result = aggregate_envelope(
            run_id="missing-instrument",
            envelope=envelope,
            candidates=[missing, candidate("structure", "MES", 20)],
            objections=[],
            rules=RULES,
        )
        self.assertNotEqual(result["outcome"], "selected")
        self.assertIn("identity_mismatch", " ".join(result["decision_trace"]))

    def test_contract_generation_lease_stale_and_evidence_fail_closed(self):
        now = datetime.now(timezone.utc)
        packet = {
            "schema_version": "glitch.direct.decision_packet.v2",
            "packet_id": "pkt-mes-replay",
            "created_utc": (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            "expires_utc": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
            "instrument": "MES",
            "account": {"name": "REPLAY"},
            "account_selection": {"selected_contract_id": "CON.F.US.MES.U26"},
            "contract": {"id": "CON.F.US.MES.U26"},
            "market": {"snapshot_hash": "b" * 64},
            "market_observation": {"timeframes": {"1m": {"close": 5000}}},
            "data_quality": {"state_complete": True, "bar_1m_closed": True, "issues": []},
            "bar_close_utc": now.isoformat().replace("+00:00", "Z"),
            "decision_scope": {"scope_hash": "scope-mes", "generation": 2},
        }
        validate_live_packet(packet, {"status": "ok"}, now=now)
        divergent = copy.deepcopy(packet)
        divergent["account_selection"]["selected_contract_id"] = "CON.F.US.MNQ.U26"
        with self.assertRaisesRegex(RunnerError, "contract_divergent"):
            validate_live_packet(divergent, {"status": "ok"}, now=now)
        expired = copy.deepcopy(packet)
        expired["expires_utc"] = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(RunnerError, "snapshot_expired"):
            validate_live_packet(expired, {"status": "ok"}, now=now)

    def test_timeout_and_absent_evidence_are_not_global_nothing(self):
        envelope = envelope_for("MCL")
        result = aggregate_envelope(
            run_id="timeout-evidence",
            envelope=envelope,
            candidates=[
                {"profile_id": "baseline-current", "state": "timeout", "instrument": "MCL", "envelope_hash": envelope["envelope_hash"]},
                {"profile_id": "structure", "state": "missing_required_evidence", "instrument": "MCL", "envelope_hash": envelope["envelope_hash"]},
            ],
            objections=[],
            rules=RULES,
        )
        self.assertNotEqual(result["decision_code"], "ENSEMBLE_UNANIMOUS_ABSTENTION")
        self.assertNotEqual(result["outcome"], "selected")


if __name__ == "__main__":
    unittest.main()
