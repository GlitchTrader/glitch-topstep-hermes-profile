"""SELECTION_EV ledger field — current-zone EV without choosing the trade in code."""

from __future__ import annotations

import math
import re
from typing import Any

SELECTION_EV_TEMPLATE = (
    "SELECTION_EV=direction=REPLACE;entry=REPLACE;stop=REPLACE;target=REPLACE;"
    "risk_points=REPLACE;reward_points=REPLACE;friction_points=REPLACE;"
    "breakeven_target_first=REPLACE;estimated_target_first_range=REPLACE;"
    "now_ev=POSITIVE|NEGATIVE|UNCERTAIN;wait_price=REPLACE;wait_ev=REPLACE;"
    "decisive_reason=REPLACE"
)

_FLAT_EV_ACTIONS = frozenset({"ENTER_LONG", "ENTER_SHORT", "NOTHING"})


def selection_ev_required(action: str | None, *, positioned: bool = False) -> bool:
    if positioned:
        return False
    return str(action or "").upper() in _FLAT_EV_ACTIONS


def extract_selection_ev(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(?mi)^SELECTION_EV\s*=\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def _selection_ev_fields(value: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in value.split(";"):
        key, separator, raw = part.partition("=")
        if separator and key.strip():
            fields[key.strip().lower()] = raw.strip()
    return fields


def _first_unsigned_number(value: Any) -> float | None:
    match = re.search(r"(?<![\d.])(?:\d+(?:[.,]\d*)?|[.,]\d+)", str(value or ""))
    if not match:
        return None
    try:
        parsed = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _selection_ev_probability(value: Any) -> float | None:
    number = _first_unsigned_number(value)
    if number is None:
        return None
    text = str(value or "")
    if "%" in text or number > 1:
        number /= 100
    return number if 0 <= number <= 1 else None


def _selection_ev_probability_range(value: Any) -> tuple[float, float] | None:
    numbers = re.findall(r"(?<![\d.])(?:\d+(?:[.,]\d*)?|[.,]\d+)", str(value or ""))
    if len(numbers) != 2:
        return None
    try:
        low, high = (float(number.replace(",", ".")) for number in numbers)
    except ValueError:
        return None
    text = str(value or "")
    if "%" in text or max(low, high) > 1:
        low /= 100
        high /= 100
    if not all(math.isfinite(number) and 0 <= number <= 1 for number in (low, high)):
        return None
    return (low, high) if low <= high else None


def _wait_claims_improvement(value: str) -> bool:
    return bool(re.search(r"(?i)\b(?:positive|improv\w*|better|dominates?)\b", value))


def validate_selection_ev(
    value: str,
    action: str,
    *,
    source: str = "decisive_evidence",
    forecast: dict[str, Any] | None = None,
) -> None:
    """Require a self-consistent EV conclusion without choosing the trade in code."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"selection_ev_missing:{source}")
    fields = _selection_ev_fields(value)
    required = {
        "direction",
        "entry",
        "stop",
        "target",
        "risk_points",
        "reward_points",
        "friction_points",
        "breakeven_target_first",
        "estimated_target_first_range",
        "now_ev",
        "wait_price",
        "wait_ev",
        "decisive_reason",
    }
    missing = sorted(key for key in required if not fields.get(key))
    if missing:
        raise ValueError(f"selection_ev_fields_missing:{source}:{','.join(missing)}")
    verdict_match = re.match(r"(?i)^\s*(POSITIVE|NEGATIVE|UNCERTAIN)\b", fields["now_ev"])
    if not verdict_match:
        raise ValueError(f"selection_ev_verdict_invalid:{source}")
    verdict = verdict_match.group(1).upper()
    action_upper = str(action or "").upper()
    if action_upper in {"ENTER_LONG", "ENTER_SHORT"} and verdict != "POSITIVE":
        raise ValueError(f"selection_ev_entry_not_positive:{source}")
    if action_upper == "NOTHING" and verdict == "POSITIVE":
        raise ValueError(f"selection_ev_nothing_positive:{source}")
    direction_match = re.match(r"(?i)^\s*(LONG|SHORT)\b", fields["direction"])
    if not direction_match:
        raise ValueError(f"selection_ev_direction_invalid:{source}")
    direction = direction_match.group(1).upper()
    if action_upper == "ENTER_LONG" and direction != "LONG":
        raise ValueError(f"selection_ev_direction_action_mismatch:{source}")
    if action_upper == "ENTER_SHORT" and direction != "SHORT":
        raise ValueError(f"selection_ev_direction_action_mismatch:{source}")

    risk = _first_unsigned_number(fields["risk_points"])
    reward = _first_unsigned_number(fields["reward_points"])
    friction = _first_unsigned_number(fields["friction_points"])
    entry = _first_unsigned_number(fields["entry"])
    stop = _first_unsigned_number(fields["stop"])
    target = _first_unsigned_number(fields["target"])
    declared_breakeven = _selection_ev_probability(fields["breakeven_target_first"])
    estimated_range = _selection_ev_probability_range(fields["estimated_target_first_range"])
    if (
        risk is None
        or risk <= 0
        or reward is None
        or reward <= 0
        or friction is None
        or friction < 0
        or entry is None
        or stop is None
        or target is None
        or declared_breakeven is None
        or estimated_range is None
    ):
        raise ValueError(f"selection_ev_numeric_invalid:{source}")
    geometry_risk = entry - stop if direction == "LONG" else stop - entry
    geometry_reward = target - entry if direction == "LONG" else entry - target
    if (
        geometry_risk <= 0
        or geometry_reward <= 0
        or abs(risk - geometry_risk) > 0.02
        or abs(reward - geometry_reward) > 0.02
    ):
        raise ValueError(f"selection_ev_geometry_mismatch:{source}")
    computed_breakeven = (risk + friction) / (risk + reward)
    if not math.isfinite(computed_breakeven) or not 0 <= computed_breakeven <= 1:
        raise ValueError(f"selection_ev_numeric_invalid:{source}")
    if abs(declared_breakeven - computed_breakeven) > 0.01:
        raise ValueError(f"selection_ev_arithmetic_mismatch:{source}")

    range_low, range_high = estimated_range
    if isinstance(forecast, dict):
        probability = forecast.get("probability")
        event = str(forecast.get("event") or "")
        if (
            event.endswith("stop_before_primary_target")
            or "STOP_BEFORE" in event.upper()
        ) and isinstance(probability, (int, float)) and not isinstance(probability, bool):
            target_first = 1 - float(probability)
            if target_first < range_low - 0.02 or target_first > range_high + 0.02:
                raise ValueError(f"selection_ev_forecast_range_mismatch:{source}")

    if (
        (verdict == "POSITIVE" and range_high < computed_breakeven - 0.005)
        or (verdict == "NEGATIVE" and range_low > computed_breakeven + 0.005)
    ):
        raise ValueError(f"selection_ev_verdict_range_mismatch:{source}")

    wait_price = _first_unsigned_number(fields["wait_price"])
    if target is not None and wait_price is not None and _wait_claims_improvement(fields["wait_ev"]):
        consumes_target = (direction == "LONG" and wait_price >= target) or (
            direction == "SHORT" and wait_price <= target
        )
        if consumes_target:
            raise ValueError(f"selection_ev_wait_consumes_target:{source}")


def validate_decisive_selection_ev(
    text: Any,
    action: str,
    *,
    positioned: bool = False,
    forecast: dict[str, Any] | None = None,
    source: str = "decisive_evidence",
) -> None:
    if not selection_ev_required(action, positioned=positioned):
        return
    value = extract_selection_ev(str(text or ""))
    if value is None:
        raise ValueError(f"selection_ev_missing:{source}")
    validate_selection_ev(value, action, source=source, forecast=forecast)
