"""Offline paper simulator — ensemble selection + hypothetical trade path (evaluation only)."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ensemble_aggregator import aggregate_envelope
from ensemble_geometry import tick_size_from_envelope

REPO = Path(__file__).resolve().parents[1]
PAPER_SCHEMA = "glitch.topstep.paper_simulation.v1"

# ponytail: block production/gateway paths at import surface — upgrade: CI ast scan like ensemble runner
FORBIDDEN_IMPORT_PREFIXES = (
    "workflows.",
    "run_topstep_cycle",
    "run-topstep-cycle",
    "intent_outbox",
    "model_owner_lock",
    "entry_delivery",
    "gateway_client",
    "gateway",
    "projectx",
    "outbox",
)

FORBIDDEN_MODULE_ROOTS = frozenset(
    {"workflows", "intent_outbox", "model_owner_lock", "entry_delivery", "gateway_client", "gateway", "projectx", "outbox"}
)


def assert_paper_simulator_isolation() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                if module == forbidden.rstrip(".") or module.startswith(forbidden):
                    raise RuntimeError(f"paper_simulator_forbidden_import:{module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULE_ROOTS:
                    raise RuntimeError(f"paper_simulator_forbidden_import:{alias.name}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _entry_price(candidate: dict[str, Any]) -> float | None:
    entry = candidate.get("entry")
    if isinstance(entry, (int, float)):
        return float(entry)
    entry_range = candidate.get("entry_range")
    if isinstance(entry_range, dict):
        low = entry_range.get("low")
        high = entry_range.get("high")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            return (float(low) + float(high)) / 2.0
    return None


def _tick_value(envelope: dict[str, Any]) -> float:
    contract = envelope.get("contract")
    if isinstance(contract, dict):
        tick_value = contract.get("tick_value")
        if isinstance(tick_value, (int, float)) and float(tick_value) > 0:
            return float(tick_value)
    packet = envelope.get("packet")
    if isinstance(packet, dict):
        nested = packet.get("contract")
        if isinstance(nested, dict):
            tick_value = nested.get("tick_value")
            if isinstance(tick_value, (int, float)) and float(tick_value) > 0:
                return float(tick_value)
    return 0.5


def normalize_profile_row(row: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """Map fixture or normalized profile output to aggregator candidate shape."""
    normalized = row.get("normalized") if isinstance(row.get("normalized"), dict) else row
    envelope_hash = str(envelope.get("envelope_hash") or envelope.get("snapshot_hash") or "")
    return {
        "profile_id": normalized.get("profile_id") or row.get("profile_id"),
        "invocation_id": str(normalized.get("invocation_id") or row.get("invocation_id") or uuid.uuid4()),
        "state": normalized.get("state") or row.get("state") or normalized.get("normalized_state"),
        "comparability": normalized.get("comparability") or row.get("comparability") or "comparable",
        "instrument": normalized.get("instrument") or row.get("instrument") or envelope.get("instrument"),
        "direction": normalized.get("direction") or row.get("direction"),
        "entry": normalized.get("entry") or row.get("entry"),
        "entry_range": normalized.get("entry_range") or row.get("entry_range"),
        "stop": normalized.get("stop") or row.get("stop"),
        "target": normalized.get("target") or row.get("target"),
        "horizon_bars": normalized.get("horizon_bars") or row.get("horizon_bars"),
        "evidence_score": normalized.get("evidence_score") or row.get("evidence_score"),
        "warning_priority_penalty": normalized.get("warning_priority_penalty") or row.get("warning_priority_penalty"),
        "error_code": normalized.get("error_code") or row.get("error_code"),
        "envelope_hash": normalized.get("envelope_hash") or row.get("envelope_hash") or envelope_hash,
        "completeness_used": normalized.get("completeness_used") or row.get("completeness_used"),
        "evidence_refs": normalized.get("evidence_refs") or row.get("evidence_refs"),
    }


def envelope_expired(envelope: dict[str, Any], *, as_of_utc: str | None = None) -> bool:
    until = str(envelope.get("valid_until_utc") or "")
    if not until:
        packet = envelope.get("packet")
        if isinstance(packet, dict):
            until = str(packet.get("expires_utc") or "")
    if not until:
        return False
    ref = parse_utc(as_of_utc or utc_now())
    until_dt = parse_utc(until)
    return ref > until_dt


def extract_chronology_bars(
    chronology: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    frame: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect high/low/close bars from path chronology or forward_observation."""
    bars: list[dict[str, Any]] = []
    if isinstance(chronology, list):
        for row in chronology:
            if isinstance(row, dict) and "high" in row and "low" in row:
                bars.append(row)
        if bars:
            return bars
    if isinstance(chronology, dict):
        nested = chronology.get("bars")
        if isinstance(nested, list):
            for row in nested:
                if isinstance(row, dict) and "high" in row and "low" in row:
                    bars.append(row)
        forward = chronology.get("forward_observation")
        if isinstance(forward, dict) and "high" in forward and "low" in forward:
            bars.append(forward)
        if bars:
            return bars
    if frame:
        forward = frame.get("forward_observation")
        if isinstance(forward, dict) and "high" in forward and "low" in forward:
            return [forward]
    return []


def simulate_trade_path(
    *,
    direction: str,
    entry: float,
    stop: float,
    target: float | None,
    bars: list[dict[str, Any]],
    tick_size: float,
    tick_value: float,
) -> dict[str, Any]:
    """First-touch stop/target simulation with MFE/MAE from chronology bars."""
    side = str(direction).lower()
    if side not in {"long", "short"}:
        raise ValueError(f"invalid_direction:{direction}")
    if not bars:
        return {
            "chronology_available": False,
            "first_touch": None,
            "exit_cause": "incomplete_data",
            "intra_bar_evidence_missing": False,
        }

    running_high = entry
    running_low = entry
    for bar in bars:
        high = float(bar["high"])
        low = float(bar["low"])
        running_high = max(running_high, high)
        running_low = min(running_low, low)

        if side == "long":
            stop_hit = low <= stop
            target_hit = target is not None and high >= float(target)
        else:
            stop_hit = high >= stop
            target_hit = target is not None and low <= float(target)

        if stop_hit and target_hit:
            return {
                "chronology_available": True,
                "first_touch": "ambiguous",
                "exit_cause": "intra_bar_ambiguous",
                "intra_bar_evidence_missing": True,
                "exit_price": None,
                "mfe_points": _mfe_points(side, entry, running_high, running_low),
                "mae_points": _mae_points(side, entry, running_high, running_low),
                "mfe_ticks": round(_mfe_points(side, entry, running_high, running_low) / tick_size, 2),
                "mae_ticks": round(_mae_points(side, entry, running_high, running_low) / tick_size, 2),
            }
        if stop_hit:
            exit_price = stop
            pnl = _pnl_points(side, entry, exit_price)
            return _path_result(
                first_touch="stop",
                exit_cause="stop",
                exit_price=exit_price,
                entry=entry,
                side=side,
                running_high=running_high,
                running_low=running_low,
                tick_size=tick_size,
                tick_value=tick_value,
                pnl_points=pnl,
            )
        if target_hit:
            exit_price = float(target)
            pnl = _pnl_points(side, entry, exit_price)
            return _path_result(
                first_touch="target",
                exit_cause="target",
                exit_price=exit_price,
                entry=entry,
                side=side,
                running_high=running_high,
                running_low=running_low,
                tick_size=tick_size,
                tick_value=tick_value,
                pnl_points=pnl,
            )

    close = float(bars[-1].get("close") or entry)
    pnl = _pnl_points(side, entry, close)
    return _path_result(
        first_touch="horizon",
        exit_cause="horizon",
        exit_price=close,
        entry=entry,
        side=side,
        running_high=running_high,
        running_low=running_low,
        tick_size=tick_size,
        tick_value=tick_value,
        pnl_points=pnl,
    )


def _mfe_points(side: str, entry: float, high: float, low: float) -> float:
    if side == "long":
        return max(0.0, high - entry)
    return max(0.0, entry - low)


def _mae_points(side: str, entry: float, high: float, low: float) -> float:
    if side == "long":
        return max(0.0, entry - low)
    return max(0.0, high - entry)


def _pnl_points(side: str, entry: float, exit_price: float) -> float:
    if side == "long":
        return exit_price - entry
    return entry - exit_price


def _path_result(
    *,
    first_touch: str,
    exit_cause: str,
    exit_price: float,
    entry: float,
    side: str,
    running_high: float,
    running_low: float,
    tick_size: float,
    tick_value: float,
    pnl_points: float,
) -> dict[str, Any]:
    mfe = _mfe_points(side, entry, running_high, running_low)
    mae = _mae_points(side, entry, running_high, running_low)
    ticks = pnl_points / tick_size
    return {
        "chronology_available": True,
        "first_touch": first_touch,
        "exit_cause": exit_cause,
        "intra_bar_evidence_missing": False,
        "entry_price": entry,
        "exit_price": exit_price,
        "mfe_points": round(mfe, 4),
        "mae_points": round(mae, 4),
        "mfe_ticks": round(mfe / tick_size, 2),
        "mae_ticks": round(mae / tick_size, 2),
        "pnl_points": round(pnl_points, 4),
        "pnl_ticks": round(ticks, 2),
        "pnl_usd": round(ticks * tick_value, 4),
        "counterfactual": True,
    }


def simulate_paper(
    *,
    envelope: dict[str, Any],
    profile_outputs: list[dict[str, Any]],
    chronology: dict[str, Any] | list[dict[str, Any]] | None = None,
    selection: dict[str, Any] | None = None,
    rules: dict[str, Any],
    run_id: str | None = None,
    objections: list[dict[str, Any]] | None = None,
    frame: dict[str, Any] | None = None,
    as_of_utc: str | None = None,
    operational_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run offline paper simulation from recorded artifacts only."""
    assert_paper_simulator_isolation()
    snapshot_before = copy.deepcopy(operational_snapshot) if operational_snapshot is not None else None
    effective_run_id = run_id or f"paper-{uuid.uuid4()}"
    envelope_hash = str(envelope.get("envelope_hash") or envelope.get("snapshot_hash") or "")

    base = {
        "schema_version": PAPER_SCHEMA,
        "run_id": effective_run_id,
        "envelope_id": str(envelope.get("envelope_id") or ""),
        "envelope_hash": envelope_hash,
        "paper_only": True,
        "promotion_use_allowed": False,
        "operational_writes": 0,
        "simulated_utc": utc_now(),
    }

    if envelope_expired(envelope, as_of_utc=as_of_utc):
        return {
            **base,
            "paper_status": "paper_expired",
            "selection": None,
            "trade_path": None,
            "rejection_reason": "envelope_expired",
        }

    candidates = [normalize_profile_row(row, envelope) for row in profile_outputs]
    agg_selection = selection or aggregate_envelope(
        run_id=effective_run_id,
        envelope=envelope,
        candidates=candidates,
        objections=objections or [],
        rules=rules,
    )

    outcome = str(agg_selection.get("outcome") or "")
    if outcome == "classified_failure":
        return {
            **base,
            "paper_status": "paper_rejected",
            "selection": agg_selection,
            "trade_path": None,
            "rejection_reason": agg_selection.get("decision_code"),
        }

    if outcome != "selected":
        return {
            **base,
            "paper_status": "paper_no_selection",
            "selection": agg_selection,
            "trade_path": None,
        }

    winner = agg_selection.get("selected_candidate")
    full_winner = next(
        (c for c in candidates if str(c.get("profile_id")) == str(agg_selection.get("selected_profile_id"))),
        winner,
    )
    candidate = full_winner or {}
    entry = _entry_price(candidate)
    stop = candidate.get("stop")
    target = candidate.get("target")
    direction = candidate.get("direction")

    if entry is None or not isinstance(stop, (int, float)) or not direction:
        return {
            **base,
            "paper_status": "paper_rejected",
            "selection": agg_selection,
            "trade_path": None,
            "rejection_reason": "incomplete_candidate_geometry",
        }

    bars = extract_chronology_bars(chronology, frame=frame)
    if not bars:
        return {
            **base,
            "paper_status": "paper_rejected",
            "selection": agg_selection,
            "trade_path": None,
            "rejection_reason": "incomplete_chronology",
        }

    tick_size = tick_size_from_envelope(envelope)
    tick_value = _tick_value(envelope)
    path = simulate_trade_path(
        direction=str(direction),
        entry=float(entry),
        stop=float(stop),
        target=float(target) if isinstance(target, (int, float)) else None,
        bars=bars,
        tick_size=tick_size,
        tick_value=tick_value,
    )

    if not path.get("chronology_available"):
        return {
            **base,
            "paper_status": "paper_rejected",
            "selection": agg_selection,
            "trade_path": path,
            "rejection_reason": path.get("exit_cause"),
        }

    if path.get("intra_bar_evidence_missing"):
        paper_status = "paper_selected"
    elif path.get("exit_cause") == "horizon":
        paper_status = "paper_selected"
    else:
        paper_status = "paper_outcome"

    result = {
        **base,
        "paper_status": paper_status,
        "selection": agg_selection,
        "trade_path": path,
        "hypothetical_entry": {
            "profile_id": agg_selection.get("selected_profile_id"),
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
        },
    }
    if snapshot_before is not None:
        result["operational_snapshot_unchanged"] = snapshot_before == operational_snapshot
    return result


def build_report(runs: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for run in runs:
        status = str(run.get("paper_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": PAPER_SCHEMA,
        "paper_only": True,
        "promotion_use_allowed": False,
        "run_count": len(runs),
        "status_counts": counts,
        "operational_writes_total": 0,
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline paper simulator (recorded artifacts only)")
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, help="JSON array of profile normalized outputs")
    parser.add_argument("--selection", type=Path, help="Precomputed aggregator selection JSON")
    parser.add_argument("--chronology", type=Path, help="Path chronology or minute-frame JSON")
    parser.add_argument("--frame", type=Path, help="Minute frame with forward_observation")
    parser.add_argument("--rules", type=Path, default=REPO / "evaluation" / "aggregator_rules.v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="Optional summary report path")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    envelope = read_json(args.envelope)
    rules = read_json(args.rules)
    profile_outputs: list[dict[str, Any]] = []
    if args.profiles:
        raw = json.loads(args.profiles.read_text(encoding="utf-8"))
        profile_outputs = raw if isinstance(raw, list) else raw.get("profiles") or []

    selection = read_json(args.selection) if args.selection and args.selection.is_file() else None
    chronology: dict[str, Any] | list[dict[str, Any]] | None = None
    frame: dict[str, Any] | None = None
    if args.chronology and args.chronology.is_file():
        chronology = json.loads(args.chronology.read_text(encoding="utf-8"))
    if args.frame and args.frame.is_file():
        frame = read_json(args.frame)

    result = simulate_paper(
        envelope=envelope,
        profile_outputs=profile_outputs,
        chronology=chronology,
        selection=selection,
        rules=rules,
        run_id=args.run_id,
        frame=frame,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.report:
        report = build_report([result])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"paper_status": result["paper_status"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
