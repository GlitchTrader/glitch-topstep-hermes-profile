"""Entry delivery — cognitive band audit + executable geometry gate."""

from __future__ import annotations

import unittest

from entry_delivery import (
    assert_entry_delivery_allowed,
    decision_reference_price,
    evaluate_entry_revalidation,
    executable_reference_with_source,
)


class EntryDeliveryTests(unittest.TestCase):
    def test_decision_reference_prefers_last(self):
        market = {"last": 21000.0, "bid": 20999.75, "ask": 21000.25}
        self.assertEqual(decision_reference_price(market), 21000.0)

    def test_long_below_band_allowed_when_geometry_executable(self):
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
        self.assertTrue(result["delivery_allowed"])
        self.assertFalse(result["range_valid"])
        self.assertEqual(result["reason"], "cognitive_band_breach_allowed")
        self.assertEqual(result["cognitive_band_breach_direction"], "favorable")
        assert_entry_delivery_allowed(intent, market)

    def test_long_above_band_allowed_when_still_below_target(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 21020.0,
            "bid": 21019.75,
            "ask": 21020.25,
        }
        result = evaluate_entry_revalidation(intent, market)
        self.assertTrue(result["delivery_allowed"])
        self.assertFalse(result["range_valid"])
        self.assertEqual(result["cognitive_band_breach_direction"], "adverse")
        assert_entry_delivery_allowed(intent, market)

    def test_short_above_band_allowed_when_geometry_executable(self):
        intent = {
            "action": "ENTER_SHORT",
            "stop_loss": 21040.0,
            "take_profit_1": 20970.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 21020.0,
            "bid": 21019.75,
            "ask": 21020.25,
        }
        result = evaluate_entry_revalidation(intent, market)
        self.assertTrue(result["delivery_allowed"])
        self.assertEqual(result["cognitive_band_breach_direction"], "favorable")

    def test_short_below_band_allowed_when_still_above_target(self):
        intent = {
            "action": "ENTER_SHORT",
            "stop_loss": 21040.0,
            "take_profit_1": 20970.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 20985.0,
            "bid": 20984.75,
            "ask": 20985.25,
        }
        result = evaluate_entry_revalidation(intent, market)
        self.assertTrue(result["delivery_allowed"])
        self.assertEqual(result["cognitive_band_breach_direction"], "adverse")

    def test_long_above_target_rejects_geometry(self):
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
        result = evaluate_entry_revalidation(intent, market)
        self.assertFalse(result["delivery_allowed"])
        self.assertEqual(result["reason"], "entry_geometry_invalid_at_latest_price")
        with self.assertRaises(ValueError) as raised:
            assert_entry_delivery_allowed(intent, market)
        self.assertEqual(str(raised.exception), "entry_geometry_invalid_at_latest_price")

    def test_short_below_target_rejects_geometry(self):
        intent = {
            "action": "ENTER_SHORT",
            "stop_loss": 21040.0,
            "take_profit_1": 20970.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {
            "last": 20960.0,
            "bid": 20959.75,
            "ask": 20960.25,
        }
        with self.assertRaises(ValueError) as raised:
            assert_entry_delivery_allowed(intent, market)
        self.assertEqual(str(raised.exception), "entry_geometry_invalid_at_latest_price")

    def test_price_on_stop_or_target_rejects(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        for ask in (20970.0, 21040.0):
            with self.subTest(ask=ask):
                market = {"last": ask, "bid": ask - 0.25, "ask": ask}
                result = evaluate_entry_revalidation(intent, market)
                self.assertFalse(result["delivery_allowed"])

    def test_missing_bbo_falls_back_to_decision_reference(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 20990.0,
            "entry_price_max": 21010.0,
        }
        market = {"last": 21000.0}
        reference, source = executable_reference_with_source(market, "ENTER_LONG")
        self.assertEqual(reference, 21000.0)
        self.assertEqual(source, "decision_last")
        result = evaluate_entry_revalidation(intent, market)
        self.assertTrue(result["delivery_allowed"])
        self.assertEqual(result["reference_source"], "decision_last")

    def test_inverted_band_rejects(self):
        intent = {
            "action": "ENTER_LONG",
            "stop_loss": 20970.0,
            "take_profit_1": 21040.0,
            "entry_price_min": 21010.0,
            "entry_price_max": 20990.0,
        }
        with self.assertRaises(ValueError) as raised:
            evaluate_entry_revalidation(intent, {"last": 21000.0, "bid": 20999.75, "ask": 21000.25})
        self.assertEqual(str(raised.exception), "entry_price_range_invalid")


if __name__ == "__main__":
    unittest.main()
