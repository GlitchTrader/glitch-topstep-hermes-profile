import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from multimarket_operational import (  # noqa: E402
    aggregate_multimarket_decision,
    MultimarketEnvelopeError,
    fetch_multimarket_cycle_envelope,
)
from prac_live_ensemble import RunnerError, decision_to_gateway_intent_v4  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
