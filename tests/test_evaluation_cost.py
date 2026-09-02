"""Tests for evaluation cost accounting."""



from __future__ import annotations



import sys

import unittest

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))



from evaluation_cost import HermesInvocationCapture, account_evaluation_cost, cost_gate_blocks_expansion





class EvaluationCostTests(unittest.TestCase):

    def test_provider_reported_cost_usd(self) -> None:

        record = account_evaluation_cost(

            prompt="hello",

            capture=HermesInvocationCapture(

                stdout='{"state":"no_edge","cost_usd":0.001}',

                stderr="session_id: abc",

                model="openai/gpt-4o-mini",

                provider="openrouter",

            ),

            parsed_output={"state": "no_edge", "cost_usd": 0.001},

        )

        self.assertEqual(record["cost_basis"], "provider_reported_cost")

        self.assertEqual(record["provider_reported_cost_usd"], 0.001)

        self.assertIsNone(record["estimated_cost_usd"])

        self.assertEqual(record["cost_usd"], 0.001)

        self.assertTrue(record["cost_gate_passed"])



    def test_estimated_tokens_when_no_provider_cost(self) -> None:

        record = account_evaluation_cost(

            prompt="x" * 4000,

            capture=HermesInvocationCapture(

                stdout='{"state":"no_edge","direction":"flat"}',

                stderr="",

                model="openai/gpt-4o-mini",

                provider="openrouter",

            ),

            parsed_output={"state": "no_edge", "direction": "flat"},

        )

        self.assertEqual(record["cost_basis"], "estimated_tokens")

        self.assertEqual(record["pricing_version"], "2026-09-01-v1")

        self.assertIsNone(record["provider_reported_cost_usd"])

        self.assertGreater(record["estimated_cost_usd"], 0.0)

        self.assertEqual(record["cost_usd"], record["estimated_cost_usd"])

        self.assertTrue(record["token_usage"]["estimated"])

        self.assertEqual(

            record["token_usage"]["input_tokens"],

            record["token_usage"]["prompt_tokens"],

        )

        self.assertTrue(record["cost_gate_passed"])



    def test_conservative_rounding_ceil(self) -> None:

        record = account_evaluation_cost(

            prompt="a",

            capture=HermesInvocationCapture(

                stdout="b",

                stderr="",

                model="openai/gpt-4o-mini",

                provider="openrouter",

            ),

        )

        self.assertEqual(record["cost_basis"], "estimated_tokens")

        self.assertEqual(record["estimated_cost_usd"], 0.000001)



    def test_unknown_model_returns_null_cost(self) -> None:

        record = account_evaluation_cost(

            prompt="hello",

            capture=HermesInvocationCapture(

                stdout='{"state":"no_edge"}',

                stderr="",

                model="unknown/model",

                provider="openrouter",

            ),

        )

        self.assertEqual(record["cost_basis"], "unknown")

        self.assertIsNone(record["cost_usd"])

        self.assertIsNone(record["estimated_cost_usd"])

        self.assertTrue(record["cost_unknown"])

        self.assertFalse(record["cost_gate_passed"])

        self.assertTrue(cost_gate_blocks_expansion(record))



    def test_session_cost_accumulation_blocks_over_budget(self) -> None:

        record = account_evaluation_cost(

            prompt="x" * 4000,

            capture=HermesInvocationCapture(

                stdout='{"state":"no_edge"}',

                stderr="",

                model="openai/gpt-4o-mini",

                provider="openrouter",

            ),

            session_cost_usd_so_far=2.499999,

        )

        self.assertFalse(record["cost_gate_passed"])



    def test_expansion_blocked_when_gate_fails(self) -> None:

        record = {

            "cost_unknown": True,

            "cost_basis": "unknown",

            "cost_status": "unknown",

            "cost_gate_passed": False,

        }

        self.assertTrue(cost_gate_blocks_expansion(record))





if __name__ == "__main__":

    unittest.main()


