"""Decision regret metrics — ENTER vs NOTHING accountability and NOW vs WAIT."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import parse_utc, read_optional_json, tail_jsonl
from selection_ev import extract_selection_ev, _selection_ev_fields, _first_unsigned_number


REGRET_SCHEMA = "glitch.topstep.decision_regret.v1"
NOW_WAIT_SCHEMA = "glitch.topstep.now_wait_regret.v1"

CLASSIFICATION_ALIASES = {
    "missed_directional_participation": "missed_edge",
    "justified_abstention": "good_abstention",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _minutes_since(value: Any, now: datetime) -> float:
    try:
        return (now - parse_utc(value)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


def _intent_payload(decision: dict[str, Any]) -> dict[str, Any]:
    intent = decision.get("intent")
    if isinstance(intent, dict):
        return intent
    return decision if isinstance(decision, dict) else {}


def _now_ev_from_decision(decision: dict[str, Any]) -> str | None:
    intent = _intent_payload(decision)
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    selection_ev = extract_selection_ev(str(audit.get("decisive_evidence") or ""))
    if not selection_ev:
        return None
    fields = _selection_ev_fields(selection_ev)
    match = re.match(
        r"(?i)^\s*(POSITIVE_ROBUST|POSITIVE_THIN|NEGATIVE|UNCERTAIN)\b",
        fields.get("now_ev", ""),
    )
    return match.group(1).upper() if match else None


def observed_path_from_frames(
    state_root: Path,
    after_utc: str,
    *,
    horizon_minutes: int = 10,
) -> tuple[float | None, float | None]:
    """High/low proxy from minute frames inside the post-decision horizon."""
    try:
        start = parse_utc(after_utc)
    except (TypeError, ValueError):
        return None, None
    end_ts = start.timestamp() + horizon_minutes * 60
    highs: list[float] = []
    lows: list[float] = []
    frames_dir = state_root / "minute-frames"
    if not frames_dir.is_dir():
        return None, None
    for path in sorted(frames_dir.glob("*.json")):
        frame = read_optional_json(path)
        if not frame:
            continue
        captured_raw = frame.get("captured_utc") or frame.get("minute_id")
        try:
            captured = parse_utc(str(captured_raw))
        except (TypeError, ValueError):
            continue
        ts = captured.timestamp()
        if ts < start.timestamp() or ts > end_ts:
            continue
        packet = frame.get("packet") if isinstance(frame.get("packet"), dict) else {}
        market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
        quote_nums: list[float] = []
        for key in ("last", "bid", "ask", "mid"):
            number = _first_unsigned_number(market.get(key))
            if number is not None:
                quote_nums.append(number)
        if quote_nums:
            highs.append(max(quote_nums))
            lows.append(min(quote_nums))
        observation = packet.get("market_observation")
        if isinstance(observation, dict):
            for bar_key in ("prior_completed_bar_1m", "current_partial_bar_1m"):
                bar = observation.get(bar_key)
                if isinstance(bar, dict):
                    high = _first_unsigned_number(bar.get("high"))
                    low = _first_unsigned_number(bar.get("low"))
                    if high is not None:
                        highs.append(high)
                    if low is not None:
                        lows.append(low)
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)


def classify_nothing_regret(
    decision: dict[str, Any],
    observed_high: float | None,
    observed_low: float | None,
) -> dict[str, Any] | None:
    intent = _intent_payload(decision)
    action = str(intent.get("action") or decision.get("action") or "").upper()
    if action != "NOTHING":
        return None
    audit = intent.get("decision_audit")
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
    decision_id = (
        decision.get("decision_id")
        or decision.get("packet_id")
        or intent.get("packet_id")
    )
    if observed_high is None or observed_low is None:
        return {
            "schema_version": REGRET_SCHEMA,
            "recorded_utc": _utc_now(),
            "decision_id": decision_id,
            "action": action,
            "classification": "ambiguous",
            "reason": "observed_path_incomplete",
            "now_ev": _now_ev_from_decision(decision),
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
    else:
        classification = "ambiguous"
    return {
        "schema_version": REGRET_SCHEMA,
        "recorded_utc": _utc_now(),
        "decision_id": decision_id,
        "action": action,
        "direction": side,
        "classification": classification,
        "alias": CLASSIFICATION_ALIASES.get(classification),
        "counterfactual_entry": entry,
        "counterfactual_stop": stop,
        "counterfactual_target": target,
        "observed_high": observed_high,
        "observed_low": observed_low,
        "now_ev": _now_ev_from_decision(decision),
    }


def classify_enter_regret(
    decision: dict[str, Any],
    fill_price: float | None,
    observed_high: float | None = None,
    observed_low: float | None = None,
) -> dict[str, Any] | None:
    intent = _intent_payload(decision)
    action = str(intent.get("action") or decision.get("action") or "").upper()
    if action not in {"ENTER_LONG", "ENTER_SHORT"}:
        return None
    stop = _first_unsigned_number(intent.get("stop_loss"))
    target = _first_unsigned_number(intent.get("take_profit_1"))
    low = _first_unsigned_number(intent.get("entry_price_min"))
    high = _first_unsigned_number(intent.get("entry_price_max"))
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
    if observed_high is not None and observed_low is not None:
        if action == "ENTER_LONG":
            if observed_low <= stop:
                classification = "bad_participation"
                reason = "stop_hit_on_observed_path"
            elif observed_high >= target:
                classification = "good_participation"
                reason = "target_reached_on_observed_path"
        else:
            if observed_high >= stop:
                classification = "bad_participation"
                reason = "stop_hit_on_observed_path"
            elif observed_low <= target:
                classification = "good_participation"
                reason = "target_reached_on_observed_path"
    return {
        "schema_version": REGRET_SCHEMA,
        "recorded_utc": _utc_now(),
        "decision_id": decision.get("decision_id") or intent.get("intent_id"),
        "action": action,
        "classification": classification,
        "reason": reason,
        "entry_band_mid": band_mid,
        "fill_price": fill_price,
        "stop_loss": stop,
        "take_profit_1": target,
        "observed_high": observed_high,
        "observed_low": observed_low,
        "now_ev": _now_ev_from_decision(decision),
    }


def classify_now_vs_wait_regret(
    decision: dict[str, Any],
    observed_high: float | None,
    observed_low: float | None,
    *,
    fill_price: float | None = None,
) -> dict[str, Any] | None:
    intent = _intent_payload(decision)
    action = str(intent.get("action") or "").upper()
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    selection_ev = extract_selection_ev(str(audit.get("decisive_evidence") or ""))
    if not selection_ev:
        return None
    fields = _selection_ev_fields(selection_ev)
    direction = re.match(r"(?i)^\s*(LONG|SHORT)", fields.get("direction", ""))
    if not direction:
        return None
    side = direction.group(1).upper()
    wait_price = _first_unsigned_number(fields.get("wait_price"))
    risk = _first_unsigned_number(fields.get("risk_points")) or 1.0
    if wait_price is None:
        return None
    now_entry = fill_price
    if now_entry is None and action in {"ENTER_LONG", "ENTER_SHORT"}:
        band_low = _first_unsigned_number(intent.get("entry_price_min"))
        band_high = _first_unsigned_number(intent.get("entry_price_max"))
        if band_low is not None and band_high is not None:
            now_entry = (band_low + band_high) / 2
    if now_entry is None:
        now_entry = _first_unsigned_number(fields.get("entry"))
    decision_id = decision.get("decision_id") or intent.get("packet_id") or intent.get("intent_id")
    if now_entry is None or observed_high is None or observed_low is None:
        return {
            "schema_version": NOW_WAIT_SCHEMA,
            "kind": "now_vs_wait",
            "recorded_utc": _utc_now(),
            "decision_id": decision_id,
            "classification": "ambiguous",
            "reason": "now_wait_inputs_incomplete",
        }
    # ponytail: materiality uses 15% of declared risk_points; upgrade: instrument tick-scaled table
    threshold = max(0.5, risk * 0.15)
    if side == "LONG":
        wait_touched = observed_low <= wait_price
        wait_improvement = now_entry - wait_price if wait_touched else 0.0
        wait_missed = observed_high >= _first_unsigned_number(fields.get("target")) if wait_touched else False
    else:
        wait_touched = observed_high >= wait_price
        wait_improvement = wait_price - now_entry if wait_touched else 0.0
        target = _first_unsigned_number(fields.get("target"))
        wait_missed = observed_low <= target if wait_touched and target is not None else False
    if wait_touched and wait_missed:
        classification = "wait_missed_trade"
        reason = "wait_price_consumed_opportunity"
    elif wait_touched and wait_improvement > threshold:
        classification = "wait_better"
        reason = "wait_price_materially_better_than_now_entry"
    elif wait_touched and wait_improvement < -threshold:
        classification = "enter_now_better"
        reason = "now_entry_materially_better_than_wait"
    elif action in {"ENTER_LONG", "ENTER_SHORT"} and not wait_touched:
        classification = "enter_now_better"
        reason = "wait_price_not_reached"
    else:
        classification = "no_material_difference"
        reason = "wait_and_now_within_material_threshold"
    return {
        "schema_version": NOW_WAIT_SCHEMA,
        "kind": "now_vs_wait",
        "recorded_utc": _utc_now(),
        "decision_id": decision_id,
        "action": action,
        "direction": side,
        "classification": classification,
        "reason": reason,
        "now_entry": now_entry,
        "wait_price": wait_price,
        "wait_improvement_points": round(wait_improvement, 4),
        "material_threshold_points": round(threshold, 4),
        "now_ev": _now_ev_from_decision(decision),
    }


def append_regret_record(root: Path, record: dict[str, Any]) -> None:
    path = root / "decision-regret.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def process_pending_regret_evaluations(
    state_root: Path,
    *,
    horizon_minutes: int = 10,
    max_age_minutes: int = 180,
) -> dict[str, Any]:
    """Evaluate matured decisions once using subsequent minute-frame path."""
    index_path = state_root / "regret-processed.json"
    index = read_optional_json(index_path) or {
        "schema_version": "glitch.topstep.regret_processed.v1",
        "processed": {},
    }
    processed = index.get("processed") if isinstance(index.get("processed"), dict) else {}
    now = datetime.now(timezone.utc)
    decisions = tail_jsonl(state_root / "decisions.jsonl", 500)
    evaluated = 0
    records_written = 0
    for row in decisions:
        if not isinstance(row, dict):
            continue
        decision_id = str(row.get("packet_id") or "")
        recorded = row.get("recorded_utc")
        if not decision_id or not recorded:
            continue
        if processed.get(decision_id):
            continue
        age_min = _minutes_since(recorded, now)
        if age_min < horizon_minutes:
            continue
        if age_min > max_age_minutes:
            processed[decision_id] = "skipped_stale"
            continue
        decision_payload = {
            "packet_id": decision_id,
            "recorded_utc": recorded,
            "intent": row.get("intent"),
        }
        observed_high, observed_low = observed_path_from_frames(
            state_root,
            recorded,
            horizon_minutes=horizon_minutes,
        )
        fill_price = None
        receipt = read_optional_json(state_root / "receipts" / f"{decision_id}.json")
        if isinstance(receipt, dict):
            result = receipt.get("result")
            if isinstance(result, dict):
                fill = result.get("fill_price") or result.get("average_fill_price")
                if isinstance(fill, (int, float)) and not isinstance(fill, bool):
                    fill_price = float(fill)
        records: list[dict[str, Any]] = []
        nothing_record = classify_nothing_regret(decision_payload, observed_high, observed_low)
        if nothing_record:
            records.append(nothing_record)
        enter_record = classify_enter_regret(
            decision_payload,
            fill_price,
            observed_high,
            observed_low,
        )
        if enter_record:
            records.append(enter_record)
        now_wait = classify_now_vs_wait_regret(
            decision_payload,
            observed_high,
            observed_low,
            fill_price=fill_price,
        )
        if now_wait:
            records.append(now_wait)
        for record in records:
            append_regret_record(state_root, record)
            records_written += 1
        processed[decision_id] = "evaluated"
        evaluated += 1
    index["processed"] = processed
    index["updated_utc"] = _utc_now()
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return {
        "schema_version": "glitch.topstep.regret_batch.v1",
        "evaluated_decisions": evaluated,
        "records_written": records_written,
    }


def summarize_regret(path: Path, *, tail: int = 200) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": REGRET_SCHEMA,
            "counts": {},
            "alias_counts": {},
            "now_ev_buckets": {},
            "now_wait_counts": {},
            "total": 0,
        }
    lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    counts: dict[str, int] = {}
    alias_counts: dict[str, int] = {}
    now_ev_buckets: dict[str, int] = {}
    now_wait_counts: dict[str, int] = {}
    for raw in lines:
        if not raw.strip():
            continue
        row = json.loads(raw)
        key = str(row.get("classification") or "unknown")
        counts[key] = counts.get(key, 0) + 1
        alias = row.get("alias") or CLASSIFICATION_ALIASES.get(key)
        if alias:
            alias_counts[alias] = alias_counts.get(alias, 0) + 1
        now_ev = row.get("now_ev")
        if isinstance(now_ev, str) and now_ev:
            now_ev_buckets[now_ev] = now_ev_buckets.get(now_ev, 0) + 1
        if row.get("kind") == "now_vs_wait" or row.get("schema_version") == NOW_WAIT_SCHEMA:
            nw = str(row.get("classification") or "unknown")
            now_wait_counts[nw] = now_wait_counts.get(nw, 0) + 1
    return {
        "schema_version": REGRET_SCHEMA,
        "counts": counts,
        "alias_counts": alias_counts,
        "now_ev_buckets": now_ev_buckets,
        "now_wait_counts": now_wait_counts,
        "total": sum(counts.values()),
    }
