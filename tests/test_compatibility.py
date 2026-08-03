import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common as common_module
import compatibility as compatibility_module


COMPATIBLE_HEALTH = {
    "schema_version": "glitch.direct.health.v2",
    "status": "ok",
    "trading_mode": "shadow",
    "compatibility": {
        "gateway_name": "glitch-topstep",
        "gateway_version": "0.1.2",
        "health_schema": "glitch.direct.health.v2",
        "intent_schemas": ["glitch.intent.v2"],
        "decision_packet_schemas": [
            "glitch.direct.decision_packet.v1",
            "glitch.direct.decision_packet.v2",
        ],
        "capabilities": [
            "packet_supported_actions",
            "position_management",
            "durable_mutation_receipts",
            "restart_reconciliation",
        ],
    },
}


class CompatibilityTests(unittest.TestCase):
    def test_profile_version_matches_distribution(self):
        self.assertEqual(
            compatibility_module.PROFILE_COMPATIBILITY["profile_version"],
            "0.1.6",
        )

    def test_compatible_health_passes(self):
        compatibility_module.verify_gateway_compatibility(COMPATIBLE_HEALTH)
        self.assertEqual(
            compatibility_module.compatibility_summary(COMPATIBLE_HEALTH),
            "compatible (profile 0.1.6, gateway 0.1.2)",
        )

    def test_missing_contract_fails_closed(self):
        with self.assertRaises(RuntimeError) as error:
            compatibility_module.verify_gateway_compatibility(
                {"schema_version": "glitch.direct.health.v2", "status": "ok"}
            )
        self.assertIn("gateway_missing_compatibility_contract", str(error.exception))

    def test_old_gateway_version_fails_closed(self):
        health = {
            **COMPATIBLE_HEALTH,
            "compatibility": {
                **COMPATIBLE_HEALTH["compatibility"],
                "gateway_version": "0.1.0",
            },
        }
        issues = compatibility_module.compatibility_issues(health)
        self.assertIn("gateway_version_too_old:0.1.0<0.1.1", issues)

    def test_missing_capability_fails_closed(self):
        health = {
            **COMPATIBLE_HEALTH,
            "compatibility": {
                **COMPATIBLE_HEALTH["compatibility"],
                "capabilities": ["packet_supported_actions"],
            },
        }
        issues = compatibility_module.compatibility_issues(health)
        self.assertTrue(any(item.startswith("capabilities_missing:") for item in issues))

    def test_gateway_feed_is_fresh_requires_compatible_health(self):
        packet = {"data_quality": {"state_complete": True, "quote_age_ms": 100}}
        with unittest.mock.patch.object(
            common_module,
            "request_json",
            side_effect=[
                (200, {"status": "ok"}),
                (200, packet),
            ],
        ), unittest.mock.patch.object(common_module, "local_token", return_value="token"):
            self.assertFalse(common_module.gateway_feed_is_fresh())

        with unittest.mock.patch.object(
            common_module,
            "request_json",
            side_effect=[
                (200, COMPATIBLE_HEALTH),
                (200, packet),
            ],
        ), unittest.mock.patch.object(common_module, "local_token", return_value="token"):
            self.assertTrue(common_module.gateway_feed_is_fresh())


if __name__ == "__main__":
    unittest.main()
