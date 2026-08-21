import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_metadata import (  # noqa: E402
    SCHEMA_VERSION,
    strip_forecast_metadata,
    validate_forecast_metadata,
)


class ForecastMetadataTests(unittest.TestCase):
    def test_validate_accepts_minimal_shape(self):
        value = validate_forecast_metadata(
            {
                "schema_version": SCHEMA_VERSION,
                "horizon_minutes": 5,
                "continuation_probability": 0.6,
                "expected_regime": "TREND_UP",
            }
        )
        self.assertEqual(value["horizon_minutes"], 5)

    def test_validate_rejects_out_of_range_probability(self):
        with self.assertRaisesRegex(ValueError, "forecast_metadata_invalid:continuation_probability"):
            validate_forecast_metadata(
                {
                    "schema_version": SCHEMA_VERSION,
                    "horizon_minutes": 5,
                    "continuation_probability": 1.2,
                }
            )

    def test_strip_removes_local_metadata(self):
        intent = {
            "action": "NOTHING",
            "forecast_metadata": {
                "schema_version": SCHEMA_VERSION,
                "horizon_minutes": 5,
            },
        }
        strip_forecast_metadata(intent)
        self.assertNotIn("forecast_metadata", intent)


if __name__ == "__main__":
    unittest.main()
