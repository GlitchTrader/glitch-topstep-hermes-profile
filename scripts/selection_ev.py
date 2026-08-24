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


def selection_ev_arithmetic_audit(
    decision_audit: Any,
    forecast: Any = None,
) -> dict[str, Any]:
    """Derive EV arithmetic consistency for learning; never alters an intent."""
    result: dict[str, Any] = {
        "schema_version": "glitch.topstep.selection_ev_arithmetic.v1",
        "status": "unavailable",
        "effect": "audit_only_no_execution_effect",
        "formula": "(risk_points + friction_points) / (risk_points + reward_points)",
    }
    if not isinstance(decision_audit, dict):
        result["reason"] = "decision_audit_missing"
        return result
    value = extract_selection_ev(str(decision_audit.get("decisive_evidence") or ""))
    if value is None:
        result["reason"] = "selection_ev_missing"
        return result
    fields = _selection_ev_fields(value)
    risk = _first_unsigned_number(fields.get("risk_points"))
    reward = _first_unsigned_number(fields.get("reward_points"))
    friction = _first_unsigned_number(fields.get("friction_points"))
    declared = _selection_ev_probability(fields.get("breakeven_target_first"))
    if (
        risk is None
        or reward is None
        or friction is None
        or declared is None
        or risk <= 0
        or reward <= 0
        or friction < 0
    ):
        result["reason"] = "selection_ev_numeric_inputs_unavailable"
        return result
    deterministic = (risk + friction) / (risk + reward)
    error = abs(declared - deterministic)
    arithmetic_status = "reconciled" if error <= 0.01 else "mismatch"
    estimated_range = _selection_ev_probability_range(fields.get("estimated_target_first_range"))
    if estimated_range is None:
        range_relation = None
    elif estimated_range[0] > deterministic + 0.01:
        range_relation = "above_break_even"
    elif estimated_range[1] < deterministic - 0.01:
        range_relation = "below_break_even"
    else:
        range_relation = "straddles_break_even"
    target_first_probability = None
    if (
        isinstance(forecast, dict)
        and (
            str(forecast.get("event") or "").upper().endswith("STOP_BEFORE_PRIMARY_TARGET")
            or "STOP_BEFORE" in str(forecast.get("event") or "").upper()
        )
        and isinstance(forecast.get("probability"), (int, float))
        and not isinstance(forecast.get("probability"), bool)
        and 0 <= float(forecast["probability"]) <= 1
    ):
        target_first_probability = 1 - float(forecast["probability"])
    forecast_range_status = "unavailable"
    if estimated_range is not None and target_first_probability is not None:
        forecast_range_status = (
            "reconciled"
            if estimated_range[0] - 0.01 <= target_first_probability <= estimated_range[1] + 0.01
            else "mismatch"
        )
    declared_now_ev = str(fields.get("now_ev") or "").strip().upper()
    verdict_match = re.match(r"(?i)^\s*(POSITIVE|NEGATIVE|UNCERTAIN)\b", declared_now_ev)
    declared_now_ev = verdict_match.group(1).upper() if verdict_match else declared_now_ev
    expected_now_ev = {
        "above_break_even": "POSITIVE",
        "below_break_even": "NEGATIVE",
        "straddles_break_even": "UNCERTAIN",
    }.get(range_relation)
    now_ev_status = (
        "reconciled"
        if expected_now_ev is not None and declared_now_ev == expected_now_ev
        else "mismatch"
        if expected_now_ev is not None and declared_now_ev
        else "unavailable"
    )
    component_statuses = (arithmetic_status, forecast_range_status, now_ev_status)
    result.update(
        {
            "status": "mismatch" if "mismatch" in component_statuses else "reconciled",
            "inputs": {
                "risk_points": risk,
                "reward_points": reward,
                "friction_points": friction,
            },
            "declared_breakeven_target_first": declared,
            "deterministic_breakeven_target_first": round(deterministic, 8),
            "absolute_error_percentage_points": round(error * 100, 4),
            "tolerance_percentage_points": 1.0,
            "arithmetic_status": arithmetic_status,
            "estimated_target_first_range": (
                {"low": estimated_range[0], "high": estimated_range[1]}
                if estimated_range is not None
                else None
            ),
            "target_first_probability_from_forecast": (
                round(target_first_probability, 8)
                if target_first_probability is not None
                else None
            ),
            "forecast_range_status": forecast_range_status,
            "range_vs_break_even": range_relation,
            "declared_now_ev": declared_now_ev or None,
            "expected_now_ev_from_range": expected_now_ev,
            "now_ev_status": now_ev_status,
        }
    )
    return result


def fill_observability(
    entry_intent: dict[str, Any] | None,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Compare planned SELECTION_EV geometry with realized fill prices (audit only)."""
    result: dict[str, Any] = {
        "schema_version": "glitch.topstep.fill_observability.v1",
        "status": "unavailable",
        "effect": "audit_only_no_execution_effect",
    }
    intent = entry_intent if isinstance(entry_intent, dict) else {}
    audit = intent.get("decision_audit") if isinstance(intent.get("decision_audit"), dict) else {}
    value = extract_selection_ev(str(audit.get("decisive_evidence") or ""))
    planned_entry = planned_stop = planned_target = None
    if value:
        fields = _selection_ev_fields(value)
        planned_entry = _first_unsigned_number(fields.get("entry"))
        planned_stop = _first_unsigned_number(fields.get("stop"))
        planned_target = _first_unsigned_number(fields.get("target"))
    actual_entry = outcome.get("entry_price")
    actual_exit = outcome.get("exit_price")
    if not isinstance(actual_entry, (int, float)) or isinstance(actual_entry, bool):
        result["reason"] = "actual_entry_unavailable"
        return result
    if planned_entry is None:
        result["reason"] = "planned_selection_ev_entry_unavailable"
        result["actual_entry_price"] = float(actual_entry)
        result["actual_exit_price"] = (
            float(actual_exit)
            if isinstance(actual_exit, (int, float)) and not isinstance(actual_exit, bool)
            else None
        )
        return result
    entry_slip = float(actual_entry) - planned_entry
    result.update(
        {
            "status": "observed",
            "planned_entry": planned_entry,
            "planned_stop": planned_stop,
            "planned_target": planned_target,
            "actual_entry_price": float(actual_entry),
            "actual_exit_price": (
                float(actual_exit)
                if isinstance(actual_exit, (int, float)) and not isinstance(actual_exit, bool)
                else None
            ),
            "entry_slip_points": round(entry_slip, 8),
            "entry_within_one_point": abs(entry_slip) <= 1.0,
        }
    )
    return result
