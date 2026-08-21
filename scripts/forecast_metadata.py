"""Optional local forecast metadata validated locally and stripped before gateway delivery."""

from __future__ import annotations

import math
from typing import Any

SCHEMA_VERSION = "glitch.topstep.forecast_metadata.v1"
REQUIRED_FIELDS = frozenset({"schema_version", "horizon_minutes"})
OPTIONAL_FIELDS = frozenset({
    "continuation_probability",
    "reversal_probability",
    "target_before_stop_probability",
    "expected_regime",
    "expected_path",
    "uncertainty",
    "identity",
})
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
ALLOWED_REGIMES = frozenset({
    "TREND_UP",
    "TREND_DOWN",
    "CHOP",
    "TRANSITION",
    "LOW_LIQUIDITY",
    "DATA_DEGRADED",
})


def _probability(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"forecast_metadata_invalid:{field}")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ValueError(f"forecast_metadata_invalid:{field}")
    return number


def validate_forecast_metadata(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("forecast_metadata_invalid")
    unknown = set(obj).difference(ALLOWED_FIELDS)
    if unknown:
        raise ValueError("forecast_metadata_unknown_fields")
    missing = REQUIRED_FIELDS.difference(obj)
    if missing:
        raise ValueError("forecast_metadata_missing_fields")
    if obj.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("forecast_metadata_schema_invalid")
    horizon = obj.get("horizon_minutes")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1 or horizon > 60:
        raise ValueError("forecast_metadata_invalid:horizon_minutes")
    validated: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "horizon_minutes": horizon,
    }
    for field in (
        "continuation_probability",
        "reversal_probability",
        "target_before_stop_probability",
    ):
        if field in obj:
            validated[field] = _probability(obj[field], field)
    regime = obj.get("expected_regime")
    if regime is not None:
        if not isinstance(regime, str) or regime not in ALLOWED_REGIMES:
            raise ValueError("forecast_metadata_invalid:expected_regime")
        validated["expected_regime"] = regime
    for field in ("expected_path", "uncertainty", "identity"):
        value = obj.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise ValueError(f"forecast_metadata_invalid:{field}")
        validated[field] = value.strip()
    return validated


def strip_forecast_metadata(intent: dict[str, Any]) -> None:
    intent.pop("forecast_metadata", None)
