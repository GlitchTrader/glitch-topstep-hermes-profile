import copy
import importlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from packet_model import (  # noqa: E402
    FRAME_SNAPSHOT_SCHEMA,
    compact_packet_evidence,
    frame_for_model,
    frame_packet_keys,
    packet_for_cycle,
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
        "market_observation": {
            "observation": {
                "schema_version": "glitch.projectx.market_observation.v1",
                "timeframes": {
                    "1m": {
                        "timeframe_minutes": 1,
                        "close": 20000,
                        "bars_received": 500,
                        "gaps": [{"missing_bars": 3}],
                        "features": {"latest_close": 20000},
                    }
                },
            }
        },
        "order_flow": {
            "observation": {
                "schema_version": "glitch.projectx.order_flow.v1",
                "windows": [
                    {"window_seconds": 15, "rolling_delta": 4},
                    {"window_seconds": 60, "rolling_delta": 12},
                    {"window_seconds": 300, "rolling_delta": 99},
                ],
                "depth": {
                    "best_bid": 19999.75,
                    "best_ask": 20000.25,
                    "spread_ticks": 2,
                    "bid_levels": [{"price": 1, "current_volume": 99}],
                    "ask_levels": [{"price": 2, "current_volume": 88}],
                },
            }
        },
        "data_quality": {"state_complete": True, "issues": []},
        "execution": {"gateway_mode": "shadow"},
        "policy": {"max_contracts": 5},
        "daily_economics": {
            "authority": "reconciled_trades",
            "trading_day_id": "2099-01-01",
            "net_daily_pnl_pct": 1.01,
            "calibration_band_pct": {"low": 0.4, "high": 2.0},
        },
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

    def test_packet_for_cycle_omits_template_and_compacts_evidence(self):
        value = packet_for_cycle(
            sample_packet(),
            profile_name="glitch-topstep",
            core_model="gpt-5.6-luna",
            prompt_version="glitch-topstep-v6",
        )
        self.assertNotIn("required_output_template", value)
        timeframes = value["market_observation"]["observation"]["timeframes"]
        self.assertEqual(timeframes[0]["features"]["latest_close"], 20000)
        self.assertNotIn("gaps", timeframes[0])
        windows = value["order_flow"]["observation"]["windows"]
        self.assertEqual(len(windows), 3)
        self.assertEqual(
            [window["window_seconds"] for window in windows],
            [15, 60, 300],
        )
        self.assertNotIn("bid_levels", value["order_flow"]["observation"]["depth"])

    def test_cycle_compact_reduces_prompt_bytes(self):
        packet = sample_packet()
        bulky = copy.deepcopy(packet)
        bulky["market_observation"]["observation"]["timeframes"]["1m"]["gaps"] = [
            {"after_utc": "a", "before_utc": "b", "missing_bars": index}
            for index in range(40)
        ]
        bulky["order_flow"]["observation"]["windows"].append(
            {"window_seconds": 300, "rolling_delta": 99, "trade_count": 500}
        )
        full_bytes = len(json.dumps(bulky, separators=(",", ":")))
        cycle_bytes = len(
            json.dumps(
                packet_for_cycle(
                    bulky,
                    profile_name="glitch-topstep",
                    core_model="gpt-5.6-luna",
                    prompt_version="glitch-topstep-v6",
                ),
                separators=(",", ":"),
            )
        )
        self.assertLess(cycle_bytes, full_bytes * 0.55)

    def test_compact_packet_evidence_keeps_features(self):
        value = compact_packet_evidence(sample_packet())
        timeframe = value["market_observation"]["observation"]["timeframes"][0]
        self.assertEqual(timeframe["features"]["latest_close"], 20000)

    def test_frame_for_model_is_compact_snapshot(self):
        value = frame_for_model(sample_frame())
        self.assertEqual(value["schema_version"], FRAME_SNAPSHOT_SCHEMA)
        self.assertEqual(value["minute_id"], "20990101T1405Z")
        self.assertEqual(value["captured_utc"], "2099-01-01T14:05:01Z")
        packet = value["packet"]
        self.assertNotIn("required_output_template", packet)
        self.assertNotIn("expires_utc", packet)
        self.assertEqual(packet["market"]["last"], 20000)
        timeframe = packet["market_observation"]["observation"]["timeframes"][0]
        self.assertEqual(timeframe["features"]["latest_close"], 20000)
        self.assertEqual(packet["order_flow"]["observation"]["windows"][1]["rolling_delta"], 12)

    def test_frame_for_model_preserves_semantic_packet_keys(self):
        packet = sample_packet()
        packet["position_state"] = {"side": "FLAT"}
        packet["protection"] = {"stop_working": False}
        frame = copy.deepcopy(sample_frame())
        frame["packet"] = packet
        snapshot = frame_for_model(frame)["packet"]
        self.assertIn("market", snapshot)
        self.assertIn("daily_economics", snapshot)
        self.assertNotIn("protection", snapshot)

    def test_frame_for_model_preserves_daily_economics(self):
        packet = sample_packet()
        frame = copy.deepcopy(sample_frame())
        frame["packet"] = packet
        snapshot = frame_for_model(frame)["packet"]
        self.assertIn("daily_economics", snapshot)
        self.assertEqual(snapshot["daily_economics"]["net_daily_pnl_pct"], 1.01)

    def test_frame_for_model_handles_missing_packet(self):
        value = frame_for_model({"minute_id": "x", "captured_utc": "y"})
        self.assertEqual(value["schema_version"], FRAME_SNAPSHOT_SCHEMA)
        self.assertEqual(value["packet"], {})

    def test_frame_packet_keys_helper(self):
        packet = sample_packet()
        self.assertIn("market", frame_packet_keys(packet))

    def test_frame_for_model_preserves_session_phase(self):
        packet = sample_packet()
        packet["session"] = {
            "entry_window_open": True,
            "must_flat_utc": "2099-01-01T20:00:00Z",
            "phase": "regular",
            "phase_authority": "exchange_calendar",
            "notes": ["ignored"],
        }
        frame = copy.deepcopy(sample_frame())
        frame["packet"] = packet
        session = frame_for_model(frame)["packet"]["session"]
        self.assertEqual(session["phase"], "regular")
        self.assertEqual(session["phase_authority"], "exchange_calendar")
        self.assertNotIn("notes", session)


if __name__ == "__main__":
    unittest.main()
