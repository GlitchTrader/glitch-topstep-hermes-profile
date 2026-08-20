import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "calibration_metrics", SCRIPTS / "calibration_metrics.py"
)
calibration_metrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(calibration_metrics)


class CalibrationMetricsTests(unittest.TestCase):
    def test_compute_session_metrics_aggregates_rates(self):
        with tempfile.TemporaryDirectory() as root:
            state_root = Path(root)
            receipts_dir = state_root / "receipts"
            frames = state_root / "minute-frames"
            supervisor = state_root / "supervisor"
            for path in (receipts_dir, frames, supervisor):
                path.mkdir(parents=True)

            (receipts_dir / "ok.json").write_text(
                json.dumps(
                    {
                        "result": {
                            "http_status": 200,
                            "body": {"executor": "ok"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            (receipts_dir / "bad.json").write_text(
                json.dumps(
                    {
                        "result": {
                            "http_status": 422,
                            "body": {"error": "intent_schema_invalid"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            (supervisor / "decision-episodes.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"classification": "missed_directional_participation"}),
                        json.dumps({"classification": "justified_abstention"}),
                    ]
                ),
                encoding="utf-8",
            )

            packet_id = "20260820T1200Z"
            packet = {
                "market_observation": {
                    "observation": {
                        "timeframes": [
                            {
                                "timeframe_minutes": 5,
                                "features": {"range_position_20": 0.90},
                            }
                        ]
                    }
                }
            }
            (frames / f"{packet_id}.json").write_text(
                json.dumps({"packet": packet}),
                encoding="utf-8",
            )
            (state_root / "decisions.jsonl").write_text(
                json.dumps(
                    {
                        "packet_id": packet_id,
                        "intent": {"action": "ENTER_LONG"},
                    }
                ),
                encoding="utf-8",
            )

            metrics = calibration_metrics.compute_session_metrics(state_root)
            self.assertEqual(metrics["schema_validity_rate"], 0.5)
            self.assertEqual(metrics["missed_participation_pct"], 0.5)
            self.assertEqual(metrics["late_entry_pct"], 1.0)


if __name__ == "__main__":
    unittest.main()
