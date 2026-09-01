import unittest

from hermes_toolsets import DEFAULT_HERMES_TOOLSETS
from safe_path import safe_path_component, safe_path_component_or_digest
from workflows.learning_evidence import episode_attributable_for_promotion
from parity import validate_protective_amendment_geometry


class Ia260901ProfileRemediationTests(unittest.TestCase):
    def test_hp01_default_toolsets_memory_only(self):
        self.assertEqual(DEFAULT_HERMES_TOOLSETS, "memory")

    def test_hp03_safe_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            safe_path_component("../packet")
        digest = safe_path_component_or_digest("../packet", prefix="pkt")
        self.assertTrue(digest.startswith("pkt-"))

    def test_hp04_move_stop_geometry_invalid_for_long(self):
        packet = {
            "market": {"last": 20000, "bid": 19999, "ask": 20001},
            "protection": {
                "stop": {"price": 19990},
                "target": {"price": 20020},
            },
        }
        with self.assertRaises(ValueError):
            validate_protective_amendment_geometry(
                "MOVE_STOP",
                {"new_stop_price": 20005},
                packet,
            )

    def test_hp06_retracted_episode_excluded_from_promotion(self):
        row = {
            "learning_eligible": True,
            "fills": [{"qty": 1}],
            "protection_status": "confirmed",
            "retracted": True,
        }
        self.assertFalse(episode_attributable_for_promotion(row))


if __name__ == "__main__":
    unittest.main()
