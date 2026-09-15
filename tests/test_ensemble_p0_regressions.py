from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

import ensemble_aggregator as agg
import ensemble_parallel_runner as runner

RULES = __import__("json").loads((ROOT / "evaluation" / "aggregator_rules.v1.json").read_text())


def envelope(instrument: str = "MNQ", contract_id: str = "CON.MNQ", valid_until: str | None = None) -> dict:
    return {
        "envelope_id": "env-p0",
        "instrument": instrument,
        "snapshot_hash": "a" * 64,
        "envelope_hash": "a" * 64,
        "valid_until_utc": valid_until,
        "contract": {"id": contract_id, "tick_size": 0.25, "min_quantity": 1, "max_quantity": 10},
        "packet": {"market": {"last": 100.0}, "contract": {"id": contract_id, "tick_size": 0.25}},
    }


def candidate(profile_id: str, *, instrument: str = "MNQ", contract_id: str = "CON.MNQ", state: str = "candidate", quantity: int | None = 1, direction: str = "long", **extra: object) -> dict:
    row = {
        "profile_id": profile_id,
        "invocation_id": f"inv:{profile_id}",
        "profile_version": "v1",
        "state": state,
        "comparability": "comparable",
        "instrument": instrument,
        "contract_id": contract_id,
        "contract_generation": "g1",
        "quantity": quantity,
        "direction": direction,
        "entry": 100.0,
        "stop": 99.0,
        "target": 102.0,
        "horizon_bars": 12,
        "envelope_hash": "a" * 64,
    }
    row.update(extra)
    return row


class EnsembleP0RegressionTests(unittest.TestCase):
    def aggregate(self, candidates: list[dict], *, env: dict | None = None, process: dict | None = None) -> dict:
        return agg.aggregate_envelope(
            run_id="p0",
            envelope=env or envelope(),
            candidates=candidates,
            rules=RULES,
            process=process,
        )

    def test_version_incompatible_is_classified_failure(self) -> None:
        result = self.aggregate([candidate("baseline-current")], process={"accepted_profile_versions": {"baseline-current": "v2"}})
        self.assertEqual((result["outcome"], result["decision_code"]), ("classified_failure", "VERSION_INCOMPATIBLE"))

    def test_delayed_result_cannot_replace_valid_result(self) -> None:
        delayed = candidate("structure", delayed=True)
        valid = candidate("baseline-current")
        result = self.aggregate([delayed, valid])
        self.assertIsNone(result["selected_profile_id"])
        self.assertIn("PROFILE_RESULT_DELAYED:structure", result["decision_trace"])

    def test_divergent_identity_is_rejected(self) -> None:
        result = self.aggregate([candidate("baseline-current", instrument="MES"), candidate("structure", instrument="MES")])
        self.assertEqual(result["decision_code"], "IDENTITY_MISMATCH")

    def test_instrument_identity_is_exact_not_case_folded(self) -> None:
        result = self.aggregate([
            candidate("baseline-current", instrument="mnq"),
            candidate("structure", instrument="mnq"),
        ])
        self.assertEqual(result["decision_code"], "IDENTITY_MISMATCH")

    def test_missing_contract_identity_is_rejected_when_envelope_announces_it(self) -> None:
        env = envelope()
        env["contract"]["generation"] = "g1"
        rows = [candidate("baseline-current"), candidate("structure")]
        for row in rows:
            row.pop("contract_id")
            row.pop("contract_generation")
        result = self.aggregate(rows, env=env)
        self.assertEqual(result["decision_code"], "CONTRACT_OUTSIDE_ENVELOPE")

    def test_contract_outside_envelope_is_rejected(self) -> None:
        result = self.aggregate([candidate("baseline-current", contract_id="CON.OTHER"), candidate("structure", contract_id="CON.OTHER")])
        self.assertEqual(result["decision_code"], "CONTRACT_OUTSIDE_ENVELOPE")

    def test_invalid_quantity_is_rejected(self) -> None:
        result = self.aggregate([candidate("baseline-current", quantity=0), candidate("structure", quantity=0)])
        self.assertEqual(result["decision_code"], "INVALID_QUANTITY")

    def test_mes_and_mcl_keep_contract_identity(self) -> None:
        for instrument in ("MES", "MCL"):
            result = self.aggregate([
                candidate("baseline-current", instrument=instrument, contract_id=f"CON.{instrument}"),
                candidate("structure", instrument=instrument, contract_id=f"CON.{instrument}"),
            ], env=envelope(instrument, f"CON.{instrument}"))
            self.assertEqual(result["outcome"], "selected")

    def test_individual_timeout_is_not_no_edge(self) -> None:
        result = self.aggregate([candidate("baseline-current", state="timeout"), candidate("structure")])
        self.assertNotEqual(result["decision_code"], "ENSEMBLE_UNANIMOUS_ABSTENTION")
        self.assertIn("PROFILE_TIMEOUT:baseline-current", result["decision_trace"])

    def test_total_timeout_remains_classified_failure(self) -> None:
        result = self.aggregate([candidate("baseline-current"), candidate("structure")], process={"ensemble_timeout": True})
        self.assertEqual((result["outcome"], result["failure_class"]), ("classified_failure", "ensemble_timeout"))

    def test_missing_profile_is_explicit(self) -> None:
        result = self.aggregate([candidate("baseline-current")], process={"missing_profiles": ["structure"]})
        self.assertEqual(result["decision_code"], "PROFILE_MISSING")

    def test_invalid_output_is_preserved_and_not_selected(self) -> None:
        result = self.aggregate([candidate("baseline-current", state="invalid"), candidate("structure", state="invalid")])
        self.assertEqual(result["decision_code"], "INSUFFICIENT_ENSEMBLE_AGREEMENT")
        self.assertIn("SCHEMA_INVALID", result["decision_trace"])

    def test_snapshot_expiry_is_classified_failure(self) -> None:
        result = self.aggregate(
            [candidate("baseline-current")],
            env=envelope(valid_until="2026-09-14T00:00:00Z"),
            process={"evaluation_utc": "2026-09-14T00:00:01Z"},
        )
        self.assertEqual((result["outcome"], result["failure_class"]), ("classified_failure", "decision_expired"))

    def test_critical_objective_objection_eliminates_only_with_rule(self) -> None:
        result = self.aggregate([candidate("baseline-current"), candidate("structure")])
        self.assertEqual(result["outcome"], "selected")
        result = agg.aggregate_envelope(
            run_id="p0-objection",
            envelope=envelope(),
            candidates=[candidate("baseline-current"), candidate("structure", evidence_score=10), candidate("smart-money", evidence_score=5)],
            rules=RULES,
            objections=[{"target_profile_id": "baseline-current", "severity": "critical", "objective_rule_match": True, "risk_code": "invalid_stop_geometry"}],
        )
        self.assertEqual(result["selected_profile_id"], "structure")

    def test_noncritical_objection_does_not_eliminate(self) -> None:
        result = agg.aggregate_envelope(
            run_id="p0-warning",
            envelope=envelope(),
            candidates=[candidate("baseline-current"), candidate("structure")],
            rules=RULES,
            objections=[{"target_profile_id": "baseline-current", "severity": "critical", "objective_rule_match": False, "risk_code": "narrative"}],
        )
        self.assertEqual(result["outcome"], "selected")

    def test_no_candidate_is_not_nothing(self) -> None:
        result = self.aggregate([])
        self.assertEqual(result["decision_code"], "NO_ELIGIBLE_CANDIDATES")

    def test_order_does_not_change_selection(self) -> None:
        rows = [candidate("structure"), candidate("baseline-current")]
        a = self.aggregate(rows)
        b = self.aggregate(list(reversed(rows)))
        self.assertEqual((a["decision_code"], a["selected_profile_id"]), (b["decision_code"], b["selected_profile_id"]))


class ParallelTimeoutRegressionTests(unittest.TestCase):
    def test_total_timeout_marks_unfinished_profile(self) -> None:
        def loader(_profile_id: str, _frame_id: str) -> dict:
            time.sleep(0.05)
            return {"state": "no_edge", "direction": "flat", "thesis": "x"}

        def builder(**kwargs: object) -> dict:
            fixture = kwargs.get("fixture") or {}
            return {"state": fixture.get("state", "error") if isinstance(fixture, dict) else "error"}

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runner, "_isolated_work_dir", side_effect=lambda *_args: Path(tmp) / "slot"):
                results = runner.run_profiles_parallel(
                    profiles=[{"profile_id": "p0"}, {"profile_id": "p1"}],
                    frame_id="f",
                    run_id="r",
                    envelope={"instrument": "MNQ", "snapshot_hash": "a" * 64},
                    gates_by_profile={"p0": {}, "p1": {}},
                    loader=loader,
                    builder=builder,
                    max_parallel_slots=1,
                    total_timeout_ms=1,
                )
        self.assertTrue(any(result.error == "ensemble_timeout" for result in results))


if __name__ == "__main__":
    unittest.main()
