import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "topstep-control" / "__init__.py"
SPEC = importlib.util.spec_from_file_location("topstep_control", PLUGIN)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ControlPluginTests(unittest.TestCase):
    def test_flatten_intent_uses_strict_risk_reducing_contract(self):
        packet = {
            "instrument": "MNQ",
            "account": {"name": "TopstepX-50K"},
            "market": {"snapshot_hash": "hash"},
        }
        value = MODULE.build_exit_intent(packet)
        self.assertEqual(value["schema_version"], "glitch.intent.v2")
        self.assertEqual(value["operator_profile"], "glitch-topstep")
        self.assertEqual(value["action"], "EXIT")
        self.assertEqual(value["decision_audit"]["final_choice"], "EXIT")
        self.assertNotIn("quantity", value)
        self.assertNotIn("stop_loss", value)

    def test_direct_worker_status_exposes_detached_worker_failure(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(
            os.environ,
            {"HERMES_HOME": root},
        ):
            path = Path(root) / "state" / "supervisor" / "direct-worker-status.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "error": "ValueError:wake_triggers_missing",
                    }
                ),
                encoding="utf-8",
            )
            status = MODULE._direct_worker_status()
        self.assertEqual(
            status,
            "failed (ValueError:wake_triggers_missing)",
        )

    def test_status_reports_gateway_compatibility(self):
        compatible_health = {
            "schema_version": "glitch.direct.health.v2",
            "status": "ok",
            "trading_mode": "shadow",
            "compatibility": {
                "gateway_name": "glitch-topstep",
                "gateway_version": "0.1.2",
                "intent_schemas": ["glitch.intent.v2"],
                "decision_packet_schemas": [
                    "glitch.direct.decision_packet.v1",
                    "glitch.direct.decision_packet.v2",
                ],
                "capabilities": [
                    "packet_supported_actions",
                    "durable_mutation_receipts",
                    "restart_reconciliation",
                ],
            },
        }
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(
            os.environ,
            {"HERMES_HOME": root},
        ), mock.patch.object(
            MODULE,
            "_request",
            side_effect=[(200, compatible_health), (200, {"account": {"name": "TopstepX-50K", "canTrade": True}})],
        ), mock.patch.object(MODULE, "_job", return_value={"enabled": False}), mock.patch.object(
            MODULE,
            "_direct_worker_status",
            return_value="ok",
        ):
            text = MODULE._status_text()
        self.assertIn("compatibility: compatible", text)

    def test_trade_blocks_incompatible_gateway(self):
        incompatible_health = {
            "schema_version": "glitch.direct.health.v2",
            "status": "ok",
            "trading_mode": "shadow",
        }
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(
            os.environ,
            {"HERMES_HOME": root},
        ), mock.patch.object(
            MODULE,
            "_request",
            return_value=(200, incompatible_health),
        ):
            with self.assertRaises(RuntimeError):
                MODULE._trade("")


if __name__ == "__main__":
    unittest.main()
