"""Entry delivery parity with Glitch NT (decision reference + favorable supersession)."""

from __future__ import annotations

import unittest

from entry_delivery import (
    assert_entry_delivery_allowed,
    decision_reference_price,
    evaluate_entry_revalidation,
)


class EntryDeliveryTests(unittest.TestCase):
    def test_decision_reference_prefers_last(self):
        market = {"last": 21000.0, "bid": 20999.75, "ask": 21000.25}
        self.assertEqual(decision_reference_price(market), 21000.0)

    def test_favorable_supersession_allows_delivery_when_executable_geometry_valid(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 20985.0,
            "bid": 20984.75,
            "ask": 20995.0,
        }
        result = evaluate_entry_revalidation(intent, market)
        self.assertTrue(result["favorable_supersession"])
        self.assertTrue(result["delivery_allowed"])
        assert_entry_delivery_allowed(intent, market)

    def test_unfavorable_outside_range_still_supersedes(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 21050.0,
            "bid": 21049.75,
            "ask": 21050.25,
        }
        with self.assertRaises(ValueError) as raised:
            assert_entry_delivery_allowed(intent, market)
        self.assertEqual(str(raised.exception), "entry_range_superseded")


if __name__ == "__main__":
    unittest.main()
