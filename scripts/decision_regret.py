"""Decision regret metrics — ENTER vs NOTHING accountability (P3)."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from selection_ev import extract_selection_ev, _selection_ev_fields, _first_unsigned_number


REGRET_SCHEMA = "glitch.topstep.decision_regret.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _counterfactual_geometry(action: str, entry: float, stop: float, target: float) -> dict[str, float]:
    if action == "ENTER_LONG":
        return {
            "risk": entry - stop,
            "reward": target - entry,
        }
    return {
        "risk": stop - entry,
        "reward": entry - target,
    }


def classify_nothing_regret(
    decision: dict[str, Any],
    observed_high: float | None,
    observed_low: float | None,
) -> dict[str, Any] | None:
    action = str(decision.get("action") or "").upper()
    if action != "NOTHING":
        return None
    audit = decision.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    evidence = audit.get("decisive_evidence")
    selection_ev = extract_selection_ev(str(evidence or ""))
    if not selection_ev:
        return None
    fields = _selection_ev_fields(selection_ev)
    direction = re.match(r"(?i)^\s*(LONG|SHORT)", fields.get("direction", ""))
    if not direction:
        return None
    side = direction.group(1).upper()
    entry = _first_unsigned_number(fields.get("entry"))
    stop = _first_unsigned_number(fields.get("stop"))
    target = _first_unsigned_number(fields.get("target"))
    if entry is None or stop is None or target is None:
        return None
    if observed_high is None or observed_low is None:
        return {
            "schema_version": REGRET_SCHEMA,
            "recorded_utc": _utc_now(),
            "decision_id": decision.get("decision_id") or decision.get("packet_id"),
            "action": action,
            "classification": "ambiguous",
            "reason": "observed_path_incomplete",
        }
    if side == "LONG":
        target_first = observed_high >= target and observed_low > stop
        stop_first = observed_low <= stop
    else:
        target_first = observed_low <= target and observed_high < stop
        stop_first = observed_high >= stop
    if target_first and not stop_first:
        classification = "missed_directional_participation"
    elif stop_first and not target_first:
        classification = "justified_abstention"
    elif not target_first and not stop_first:
        classification = "ambiguous"
    else:
        classification = "ambiguous"
    return {
        "schema_version": REGRET_SCHEMA,
        "recorded_utc": _utc_now(),
        "decision_id": decision.get("decision_id") or decision.get("packet_id"),
        "action": action,
        "direction": side,
        "classification": classification,
        "counterfactual_entry": entry,
        "counterfactual_stop": stop,
        "counterfactual_target": target,
        "observed_high": observed_high,
        "observed_low": observed_low,
    }


def classify_enter_regret(
    decision: dict[str, Any],
    fill_price: float | None,
) -> dict[str, Any] | None:
    action = str(decision.get("action") or "").upper()
    if action not in {"ENTER_LONG", "ENTER_SHORT"}:
        return None
    stop = _first_unsigned_number(decision.get("stop_loss"))
    target = _first_unsigned_number(decision.get("take_profit_1"))
    low = _first_unsigned_number(decision.get("entry_price_min"))
    high = _first_unsigned_number(decision.get("entry_price_max"))
    if stop is None or target is None or low is None or high is None:
        return None
    band_mid = (low + high) / 2
    classification = "good_participation"
    reason = "fill_within_declared_band"
    if fill_price is not None and math.isfinite(fill_price):
        if action == "ENTER_LONG" and fill_price > band_mid:
            classification = "late_participation"
            reason = "fill_above_band_mid"
        elif action == "ENTER_SHORT" and fill_price < band_mid:
            classification = "late_participation"
            reason = "fill_below_band_mid"
    return {
        "schema_version": REGRET_SCHEMA,
        "recorded_utc": _utc_now(),
        "decision_id": decision.get("decision_id") or decision.get("intent_id"),
        "action": action,
        "classification": classification,
        "reason": reason,
        "entry_band_mid": band_mid,
        "fill_price": fill_price,
        "stop_loss": stop,
        "take_profit_1": target,
    }


def append_regret_record(root: Path, record: dict[str, Any]) -> None:
    path = root / "decision-regret.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def summarize_regret(path: Path, *, tail: int = 200) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": REGRET_SCHEMA, "counts": {}, "total": 0}
    lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    counts: dict[str, int] = {}
    for raw in lines:
        if not raw.strip():
            continue
        row = json.loads(raw)
        key = str(row.get("classification") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema_version": REGRET_SCHEMA,
        "counts": counts,
        "total": sum(counts.values()),
    }
