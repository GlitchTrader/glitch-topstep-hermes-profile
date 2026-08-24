"""Contract: entry bands price decision-to-delivery drift once (NT parity)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EntryDriftContractTests(unittest.TestCase):
    def test_build_intent_skill_prices_delivery_drift_once(self):
        text = (ROOT / "skills" / "topstep-build-intent" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Price plausible decision-to-delivery drift once", text)
        self.assertIn("not a one-tick quote", text)
        self.assertIn("never widen the range merely to defeat revalidation", text)

    def test_cycle_prompt_prices_delivery_drift_once(self):
        text = (ROOT / "scripts" / "run-topstep-cycle.py").read_text(encoding="utf-8")
        self.assertIn("price plausible decision-to-delivery drift once", text)
        self.assertIn("not a one-tick quote", text)

    def test_soul_requires_delivery_drift_in_entry_band(self):
        text = (ROOT / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("decision-to-delivery drift once", text)


if __name__ == "__main__":
    unittest.main()
