import copy
import json
import os
import sys
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from multimarket_operational import (  # noqa: E402
    aggregate_multimarket_decision,
    build_profile_envelope,
    MultimarketEnvelopeError,
    fetch_multimarket_cycle_envelope,
)
from prac_live_ensemble import RunnerError, decision_to_gateway_intent_v4  # noqa: E402
import prac_live_ensemble as runner  # noqa: E402
from ensemble_skill_gate import default_glitch_topstep_hermes_home, SkillPreloadError  # noqa: E402


STAMP = "2099-01-01T14:00:00Z"
CONTRACTS = {
    "MNQ": ("CON.F.US.MNQ.Z26", "F.US.MNQ", 0.25, 0.5),
    "MES": ("CON.F.US.MES.Z26", "F.US.MES", 0.25, 1.25),
    "MCL": ("CON.F.US.MCLE.V26", "F.US.MCLE", 0.01, 1.0),
}


def scanner() -> dict:
    return {
        "schema_version": "glitch.topstep.market_universe.v1",
        "generated_utc": STAMP,
        "simultaneous_exposure_enabled": False,
        "candidates": [
            {
                "instrument": instrument,
                "contract_id": values[0],
                "symbol_id": values[1],
                "tick_size": values[2],
                "tick_value": values[3],
                "observation_quality": {"status": "ready", "observation_ready": True},
                "state_complete": True,
                "state_issues": [],
            }
            for instrument, values in CONTRACTS.items()
        ],
    }


def packet(instrument: str) -> dict:
    contract_id, symbol_id, tick_size, tick_value = CONTRACTS[instrument]
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": f"packet-{instrument}",
        "created_utc": STAMP,
        "expires_utc": "2099-01-01T15:00:00Z",
        "instrument": instrument,
        "account": {"id": 7, "name": "SIM"},
        "contract": {"id": contract_id, "symbol_id": symbol_id, "tick_size": tick_size, "tick_value": tick_value, "active_contract": True},
        "market": {"snapshot_hash": f"hash-{instrument}", "quote_timestamp": STAMP, "bid": 1, "ask": 2},
        "decision_scope": {"scope_hash": f"scope-{instrument}", "generation": 2},
        "data_quality": {"state_complete": True, "issues": []},
    }


class MultimarketOperationalEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packets = {instrument: packet(instrument) for instrument in CONTRACTS}

    def request(self, path: str, **_: object):
        if path == "/scanner":
            return 200, scanner()
        if path == "/packet":
            return 200, self.packets["MNQ"]
        instrument = path.split("=", 1)[1]
        return 200, self.packets[instrument]

    def test_fetches_three_exact_packets_and_preserves_identity(self):
        result = fetch_multimarket_cycle_envelope(
            token="opaque", health={"status": "ok"}, request=self.request,
            now=datetime(2099, 1, 1, 14, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(result["schema_version"], "glitch.topstep.multimarket.envelope.v1")
        self.assertEqual(set(result["packets_by_instrument"]), {"MNQ", "MES", "MCL"})
        self.assertEqual(result["packets_by_instrument"]["MCL"]["contract"]["symbol_id"], "F.US.MCLE")
        self.assertFalse(result["simultaneous_exposure_enabled"])

    def test_rejects_contract_instrument_and_quality_divergence(self):
        for mutation, code in (
            (lambda doc: doc["candidates"][1].update({"contract_id": "CON.WRONG"}), "packet_contract_divergent:MES"),
            (lambda doc: doc["candidates"].pop(), "candidate_universe_incomplete"),
            (lambda doc: doc.update({"simultaneous_exposure_enabled": True}), "simultaneous_exposure_enabled"),
        ):
            with self.subTest(code=code):
                original = scanner
                mutated = original()
                mutation(mutated)
                def request(path: str, **kwargs: object):
                    if path == "/scanner":
                        return 200, mutated
                    if path == "/packet":
                        return 200, self.packets["MNQ"]
                    return 200, self.packets[path.split("=", 1)[1]]
                with self.assertRaisesRegex(MultimarketEnvelopeError, code):
                    fetch_multimarket_cycle_envelope(token="opaque", health={"status": "ok"}, request=request)

    def test_global_selection_preserves_mes_identity_through_v4_handoff(self):
        envelope = {
            "schema_version": "glitch.topstep.multimarket.envelope.v1",
            "envelope_id": "env-1",
            "envelope_hash": "env-hash",
            "packets_by_instrument": {key: value for key, value in self.packets.items()},
        }
        candidates = [
            {
                "profile_id": f"profile-{index}",
                "profile_version": "v1",
                "invocation_id": f"inv-{index}",
                "instrument": "MES",
                "contract_id": CONTRACTS["MES"][0],
                "symbol_id": CONTRACTS["MES"][1],
                "direction": "long",
                "evidence_score": 10,
                "entry": 5000.0,
                "stop": 4995.0,
                "target": 5010.0,
                "quantity": 1,
                "prompt_version": "glitch-topstep-v17.3",
                "model_version": "test-model",
                "thesis": "MES global thesis",
                "decision_audit": {
                    key: "evidence" for key in (
                        "bull_case", "bear_case", "flat_case", "aggressive_case",
                        "conservative_case", "decisive_evidence", "disconfirming_evidence",
                        "change_condition",
                    )
                } | {"final_choice": "ENTER_LONG"},
            }
            for index in (1, 2)
        ]
        decision = aggregate_multimarket_decision(envelope=envelope, candidates=candidates, run_id="run-1")
        decision["decision_id"] = "decision-1"
        intent = decision_to_gateway_intent_v4(decision, envelope)
        self.assertEqual(intent["schema_version"], "glitch.intent.v4")
        self.assertEqual(intent["instrument"], "MES")
        self.assertEqual(intent["contract_id"], CONTRACTS["MES"][0])
        self.assertEqual(intent["symbol_id"], CONTRACTS["MES"][1])
        self.assertEqual(intent["selected_candidate_handoff"]["selected_instrument"], "MES")
        self.assertEqual(intent["selected_candidate_handoff"]["executable_contract_id"], CONTRACTS["MES"][0])

    def test_no_selection_never_creates_entry_handoff(self):
        envelope = {
            "schema_version": "glitch.topstep.multimarket.envelope.v1",
            "packets_by_instrument": {key: value for key, value in self.packets.items()},
        }
        decision = {"outcome": "no_selection"}
        with self.assertRaisesRegex(RunnerError, "decision_missing_global_selection"):
            decision_to_gateway_intent_v4(decision, envelope)

    def test_profile_envelope_keeps_global_identity_and_all_exact_packets(self):
        operational = fetch_multimarket_cycle_envelope(
            token="opaque", health={"status": "ok"}, request=self.request,
            now=datetime(2099, 1, 1, 14, 1, tzinfo=timezone.utc),
        )
        matrix = __import__("json").loads((ROOT / "evaluation" / "capability-matrix.json").read_text())
        mapping = __import__("json").loads((ROOT / "evaluation" / "packet_envelope_mapping.v1.json").read_text())
        envelope = build_profile_envelope(
            operational,
            source_catalog=matrix["source_catalog"],
            mapping=mapping,
            validity_seconds=120,
        )
        self.assertEqual(envelope["schema_version"], "glitch.topstep.multimarket.envelope.v1")
        self.assertEqual(set(envelope["packets_by_instrument"]), {"MNQ", "MES", "MCL"})
        self.assertEqual(envelope["packets_by_instrument"]["MES"]["contract"]["id"], CONTRACTS["MES"][0])
        self.assertEqual(envelope["packets_by_instrument"]["MCL"]["contract"]["symbol_id"], "F.US.MCLE")
        self.assertFalse(envelope["simultaneous_exposure_enabled"])
        self.assertEqual(envelope["exposure_limit"], 1)

    def test_hermes_home_rejects_ambient_root_or_alternate_profile(self):
        previous_local = os.environ.get("LOCALAPPDATA")
        previous_home = os.environ.get("GLITCH_TOPSTEP_HERMES_HOME")
        try:
            os.environ["LOCALAPPDATA"] = r"C:\Operator\AppData\Local"
            os.environ["GLITCH_TOPSTEP_HERMES_HOME"] = r"C:\Operator\AppData\Local\hermes"
            with self.assertRaisesRegex(SkillPreloadError, "hermes_home_profile_mismatch"):
                default_glitch_topstep_hermes_home()
        finally:
            if previous_local is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous_local
            if previous_home is None:
                os.environ.pop("GLITCH_TOPSTEP_HERMES_HOME", None)
            else:
                os.environ["GLITCH_TOPSTEP_HERMES_HOME"] = previous_home

    def test_operational_ensemble_uses_one_run_and_six_profile_slots(self):
        operational = fetch_multimarket_cycle_envelope(
            token="opaque", health={"status": "ok"}, request=self.request,
            now=datetime(2099, 1, 1, 14, 1, tzinfo=timezone.utc),
        )
        matrix = json.loads((ROOT / "evaluation" / "capability-matrix.json").read_text())
        envelope = build_profile_envelope(
            operational,
            source_catalog=matrix["source_catalog"],
            mapping=json.loads((ROOT / "evaluation" / "packet_envelope_mapping.v1.json").read_text()),
            validity_seconds=120,
        )
        audit = {key: "evidence" for key in (
            "bull_case", "bear_case", "flat_case", "aggressive_case", "conservative_case",
            "decisive_evidence", "disconfirming_evidence", "change_condition",
        )} | {"final_choice": "ENTER_LONG"}
        seen: list[str] = []

        def fake_profiles(**kwargs):
            seen.extend(row["profile_id"] for row in json.loads((ROOT / "evaluation" / "registry.json").read_text())["profiles"])
            rows = []
            for profile_id in runner.PROFILE_IDS:
                candidate = {
                    "profile_id": profile_id,
                    "profile_version": "v1",
                    "invocation_id": f"inv-{profile_id}",
                    "state": "candidate" if profile_id in {"baseline-current", "structure"} else "no_edge",
                    "comparability": "comparable" if profile_id in {"baseline-current", "structure"} else "not_comparable",
                    "instrument": "MES",
                    "contract_id": CONTRACTS["MES"][0],
                    "symbol_id": CONTRACTS["MES"][1],
                    "direction": "long",
                    "evidence_score": 10,
                    "entry": 5000.0,
                    "stop": 4995.0,
                    "target": 5010.0,
                    "quantity": 1,
                    "prompt_version": "glitch-topstep-v17.3",
                    "model_version": "test-model",
                    "thesis": "MES global thesis",
                    "decision_audit": audit,
                    "envelope_hash": envelope["envelope_hash"],
                    "completeness_used": {},
                    "evidence_refs": ["quote:MES"],
                }
                rows.append({"profile_id": profile_id, "invocation_id": candidate["invocation_id"], "normalized": candidate, "raw_profile_output": {"state": candidate["state"]}})
            return rows

        with mock.patch.object(runner, "fetch_live_multimarket_envelope", return_value=operational), mock.patch.object(runner, "run_profiles", side_effect=fake_profiles):
            result = runner.run_operational_ensemble(health={"status": "ok"}, token="opaque", run_id="global-run")
        self.assertEqual(result["run_id"], "global-run")
        self.assertEqual(set(seen), set(runner.PROFILE_IDS))
        self.assertEqual(result["decision"]["outcome"], "selected")
        self.assertEqual(result["decision"]["selected_instrument"], "MES")
        self.assertEqual(result["intent"]["schema_version"], "glitch.intent.v4")
        self.assertEqual(result["intent"]["symbol_id"], "F.US.MES")
        self.assertEqual(result["orders_sent"], 0)


if __name__ == "__main__":
    unittest.main()
