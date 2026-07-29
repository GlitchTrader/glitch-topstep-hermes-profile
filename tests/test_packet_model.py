import copy
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from packet_model import (  # noqa: E402
    FRAME_SNAPSHOT_SCHEMA,
    frame_for_model,
    frame_packet_keys,
    packet_for_model,
)


def sample_packet() -> dict:
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": "packet-5",
        "created_utc": "2099-01-01T14:05:00Z",
        "expires_utc": "2099-01-01T15:00:00Z",
        "venue": "projectx",
        "firm": "topstep",
        "instrument": "MNQ",
        "account": {"id": 123, "name": "TopstepX-50K", "balance": 1000},
        "contract": {
            "id": "CON",
            "symbol_id": "F.US.MNQ",
            "name": "MNQ U99",
            "tick_size": 0.25,
        },
        "market": {"last": 20000, "snapshot_hash": "hash-1"},
        "market_observation": {"observation": {"timeframes": {"1m": {"close": 20000}}}},
        "order_flow": {"rolling_windows": {"30s": {"delta": 12}}},
        "data_quality": {"state_complete": True, "issues": []},
        "execution": {"gateway_mode": "shadow"},
        "policy": {"max_contracts": 5},
        "required_output_template": {
            "schema_version": "glitch.intent.v2",
            "action": "NOTHING",
        },
    }


def sample_frame() -> dict:
    return {
        "schema_version": "glitch.topstep.minute_frame.v2",
        "minute_id": "20990101T1405Z",
        "captured_utc": "2099-01-01T14:05:01Z",
        "packet": sample_packet(),
    }


class PacketModelTests(unittest.TestCase):
    def test_packet_for_model_strips_ids_and_keeps_template(self):
        value = packet_for_model(
            sample_packet(),
            profile_name="glitch-topstep",
            core_model="gpt-5.6-luna",
            prompt_version="glitch-topstep-v2",
        )
        self.assertNotIn("id", value["account"])
        self.assertNotIn("id", value["contract"])
        self.assertNotIn("symbol_id", value["contract"])
        self.assertIn("required_output_template", value)
        self.assertEqual(
            value["required_output_template"]["operator_profile"],
            "glitch-topstep",
        )
        self.assertNotIn("expires_utc", value)

    def test_frame_for_model_is_compact_snapshot(self):
        value = frame_for_model(sample_frame())
        self.assertEqual(value["schema_version"], FRAME_SNAPSHOT_SCHEMA)
        self.assertEqual(value["minute_id"], "20990101T1405Z")
        self.assertEqual(value["captured_utc"], "2099-01-01T14:05:01Z")
        packet = value["packet"]
        self.assertNotIn("required_output_template", packet)
        self.assertNotIn("expires_utc", packet)
        self.assertEqual(packet["market"]["last"], 20000)
        self.assertEqual(
            packet["market_observation"]["observation"]["timeframes"]["1m"]["close"],
            20000,
        )
        self.assertEqual(packet["order_flow"]["rolling_windows"]["30s"]["delta"], 12)

    def test_frame_for_model_preserves_semantic_packet_keys(self):
        packet = sample_packet()
        packet["position_state"] = {"side": "FLAT"}
        packet["protection"] = {"stop_working": False}
        frame = copy.deepcopy(sample_frame())
        frame["packet"] = packet
        snapshot = frame_for_model(frame)["packet"]
        self.assertEqual(frame_packet_keys(snapshot), frame_packet_keys(packet))

    def test_frame_for_model_handles_missing_packet(self):
        value = frame_for_model({"minute_id": "x", "captured_utc": "y"})
        self.assertEqual(value["schema_version"], FRAME_SNAPSHOT_SCHEMA)
        self.assertEqual(value["packet"], {})


if __name__ == "__main__":
    unittest.main()
