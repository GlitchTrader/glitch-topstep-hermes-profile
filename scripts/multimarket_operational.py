"""Read-only multimarket envelope for the operational shadow lane."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable


EXPECTED_INSTRUMENTS = ("MNQ", "MES", "MCL")
MCL_SYMBOL = "F.US.MCLE"
ENVELOPE_SCHEMA = "glitch.topstep.multimarket.envelope.v1"


class MultimarketEnvelopeError(ValueError):
    """Fail-closed validation error for the global observation envelope."""


def aggregate_multimarket_decision(
    *,
    envelope: dict[str, Any],
    candidates: list[dict[str, Any]],
    objections: list[dict[str, Any]] | None = None,
    required_profile_ids: list[str] | None = None,
    run_id: str,
) -> dict[str, Any]:
    """Select at most one instrument from one global profile result set."""
    if envelope.get("schema_version") != ENVELOPE_SCHEMA:
        raise MultimarketEnvelopeError("envelope_schema_invalid")
    packets = envelope.get("packets_by_instrument")
    if not isinstance(packets, dict):
        raise MultimarketEnvelopeError("envelope_packets_missing")
    required = set(required_profile_ids or [])
    rows = [copy.deepcopy(row) for row in candidates if isinstance(row, dict)]
    trace: list[str] = []
    preserved: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for row in rows:
        instrument = str(row.get("instrument") or "").upper()
        packet = packets.get(instrument)
        if not isinstance(packet, dict):
            row["comparability"] = "not_comparable"
            row["error_code"] = "candidate_instrument_unknown"
        elif row.get("state") in {"timeout", "error", "invalid", "missing_required_evidence", "data_quality_insufficient"}:
            row["comparability"] = "not_comparable"
        else:
            contract = packet.get("contract") if isinstance(packet.get("contract"), dict) else {}
            if str(row.get("contract_id") or "") != str(contract.get("id") or ""):
                row["comparability"] = "not_comparable"
                row["error_code"] = "contract_outside_envelope"
            elif row.get("symbol_id") is not None and str(row.get("symbol_id")) != str(contract.get("symbol_id") or ""):
                row["comparability"] = "not_comparable"
                row["error_code"] = "symbol_outside_envelope"
            elif row.get("snapshot_hash") is not None and str(row.get("snapshot_hash")) != str((packet.get("market") or {}).get("snapshot_hash") or ""):
                row["comparability"] = "not_comparable"
                row["error_code"] = "snapshot_outside_envelope"
            else:
                valid.append(row)
        preserved.append(row)
    present = {str(row.get("profile_id") or "") for row in rows}
    missing = sorted(required - present)
    if missing:
        trace.append("PROFILE_MISSING:" + ",".join(missing))
        outcome, code = "no_selection", "PROFILE_MISSING"
    elif rows and all(str(row.get("state") or "") == "timeout" for row in rows):
        trace.append("ENSEMBLE_TIMEOUT")
        outcome, code = "ensemble_timeout", "ENSEMBLE_TIMEOUT"
    else:
        objections = objections or []
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in valid:
            if any(obj.get("target_profile_id") == row.get("profile_id") and obj.get("severity") == "critical" and obj.get("objective_rule_match") is True for obj in objections):
                row["comparability"] = "not_comparable"
                continue
            key = (str(row.get("instrument")), str(row.get("contract_id")), str(row.get("direction")))
            groups.setdefault(key, []).append(row)
        ranked = sorted(
            groups.items(),
            key=lambda item: (-len(item[1]), -sum(int(row.get("evidence_score") or 0) for row in item[1]), item[0]),
        )
        trace.append("RANKING:" + ",".join(key[0] for key, _ in ranked))
        if not ranked or len(ranked[0][1]) < 2 or (len(ranked) > 1 and len(ranked[0][1]) == len(ranked[1][1]) and sum(int(row.get("evidence_score") or 0) for row in ranked[0][1]) == sum(int(row.get("evidence_score") or 0) for row in ranked[1][1])):
            outcome, code = "no_selection", "INSUFFICIENT_GLOBAL_AGREEMENT"
        else:
            key, group = ranked[0]
            winner = sorted(group, key=lambda row: (-int(row.get("evidence_score") or 0), str(row.get("profile_id") or "")))[0]
            trace.append("GLOBAL_SELECTION:" + key[0] + ":" + key[1])
            result = {
                "schema_version": "glitch.topstep.multimarket.selection.v1",
                "run_id": run_id,
                "outcome": "selected",
                "decision_code": "GLOBAL_EVIDENCE_SCORE_WIN",
                "selected_instrument": key[0],
                "selected_contract_id": key[1],
                "selected_profile_id": winner.get("profile_id"),
                "selected_candidate_full": winner,
                "ranking": [key[0] for key, _ in ranked],
                "candidates_preserved": preserved,
                "objections": copy.deepcopy(objections),
                "decision_trace": trace,
                "envelope_id": envelope.get("envelope_id"),
                "envelope_hash": envelope.get("envelope_hash"),
                "execution_authority": "gateway_only",
            }
            return result
    return {
        "schema_version": "glitch.topstep.multimarket.selection.v1",
        "run_id": run_id,
        "outcome": outcome,
        "decision_code": code,
        "selected_instrument": None,
        "selected_contract_id": None,
        "selected_profile_id": None,
        "selected_candidate_full": None,
        "ranking": [],
        "candidates_preserved": preserved,
        "objections": copy.deepcopy(objections or []),
        "decision_trace": trace,
        "envelope_id": envelope.get("envelope_id"),
        "envelope_hash": envelope.get("envelope_hash"),
        "execution_authority": "gateway_only",
    }


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MultimarketEnvelopeError(f"{field}_missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise MultimarketEnvelopeError(f"{field}_invalid") from exc


def _identity(candidate: dict[str, Any], *, prefix: str) -> tuple[str, str, str]:
    instrument = str(candidate.get("instrument") or "").strip().upper()
    contract_id = str(candidate.get("contract_id") or "").strip()
    symbol_id = str(candidate.get("symbol_id") or "").strip()
    if not instrument or not contract_id or not symbol_id:
        raise MultimarketEnvelopeError(f"{prefix}_identity_missing")
    if instrument == "MCL" and symbol_id != MCL_SYMBOL:
        raise MultimarketEnvelopeError(f"{prefix}_mcl_symbol_invalid")
    if instrument not in EXPECTED_INSTRUMENTS:
        raise MultimarketEnvelopeError(f"{prefix}_instrument_unknown")
    return instrument, contract_id, symbol_id


def _validate_candidate(candidate: Any, *, now: datetime | None) -> tuple[str, str, str]:
    if not isinstance(candidate, dict):
        raise MultimarketEnvelopeError("scanner_candidate_invalid")
    instrument, contract_id, symbol_id = _identity(candidate, prefix="scanner_candidate")
    quality = candidate.get("observation_quality")
    if not isinstance(quality, dict) or quality.get("observation_ready") is not True:
        raise MultimarketEnvelopeError(f"candidate_not_ready:{instrument}")
    if candidate.get("state_complete") is not True or candidate.get("state_issues"):
        raise MultimarketEnvelopeError(f"candidate_quality_invalid:{instrument}")
    if candidate.get("active_contract") is False:
        raise MultimarketEnvelopeError(f"candidate_contract_inactive:{instrument}")
    return instrument, contract_id, symbol_id


def _validate_packet(packet: Any, expected: tuple[str, str, str], *, now: datetime | None) -> None:
    if not isinstance(packet, dict):
        raise MultimarketEnvelopeError("packet_invalid")
    if packet.get("schema_version") != "glitch.direct.decision_packet.v2":
        raise MultimarketEnvelopeError("packet_schema_invalid")
    instrument, contract_id, symbol_id = expected
    if str(packet.get("instrument") or "").upper() != instrument:
        raise MultimarketEnvelopeError(f"packet_instrument_divergent:{instrument}")
    contract = packet.get("contract")
    if not isinstance(contract, dict) or str(contract.get("id") or "") != contract_id:
        raise MultimarketEnvelopeError(f"packet_contract_divergent:{instrument}")
    if str(contract.get("symbol_id") or "") != symbol_id or contract.get("active_contract") is False:
        raise MultimarketEnvelopeError(f"packet_contract_invalid:{instrument}")
    market = packet.get("market")
    quality = packet.get("data_quality")
    if not isinstance(market, dict) or not market.get("snapshot_hash"):
        raise MultimarketEnvelopeError(f"packet_snapshot_missing:{instrument}")
    if not isinstance(market.get("quote_timestamp"), str):
        raise MultimarketEnvelopeError(f"packet_quote_missing:{instrument}")
    if not isinstance(quality, dict) or quality.get("state_complete") is not True:
        raise MultimarketEnvelopeError(f"packet_state_incomplete:{instrument}")
    if now is not None and _utc(packet.get("expires_utc"), f"packet_expires:{instrument}") <= now:
        raise MultimarketEnvelopeError(f"packet_expired:{instrument}")


def fetch_multimarket_cycle_envelope(
    *,
    token: str,
    health: dict[str, Any],
    request: Callable[..., tuple[int, dict[str, Any]]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch and validate one global, read-only envelope from packet + scanner."""
    if not isinstance(health, dict) or health.get("status") not in {"ok", "ready", "degraded"}:
        raise MultimarketEnvelopeError("health_invalid")
    status, base_packet = request("/packet", token=token)
    if status != 200:
        raise MultimarketEnvelopeError(f"packet_request_failed:{status}")
    status, scanner = request("/scanner", token=token)
    if status != 200 or not isinstance(scanner, dict):
        raise MultimarketEnvelopeError(f"scanner_request_failed:{status}")
    if scanner.get("schema_version") != "glitch.topstep.market_universe.v1":
        raise MultimarketEnvelopeError("scanner_schema_invalid")
    scanner_time = _utc(scanner.get("generated_utc"), "scanner_generated")
    candidates = scanner.get("candidates")
    if not isinstance(candidates, list):
        raise MultimarketEnvelopeError("scanner_candidates_missing")
    by_instrument: dict[str, tuple[str, str, str]] = {}
    for candidate in candidates:
        identity = _validate_candidate(candidate, now=now)
        instrument = identity[0]
        if instrument in by_instrument:
            raise MultimarketEnvelopeError(f"candidate_collision:{instrument}")
        by_instrument[instrument] = identity
    if tuple(sorted(by_instrument)) != tuple(sorted(EXPECTED_INSTRUMENTS)):
        raise MultimarketEnvelopeError("candidate_universe_incomplete")

    packets: dict[str, dict[str, Any]] = {}
    for instrument in EXPECTED_INSTRUMENTS:
        identity = by_instrument[instrument]
        if str(base_packet.get("instrument") or "").upper() == instrument:
            packet = base_packet
        else:
            packet_status, packet = request(f"/packet?instrument={instrument}", token=token)
            if packet_status != 200:
                raise MultimarketEnvelopeError(f"packet_request_failed:{instrument}:{packet_status}")
        _validate_packet(packet, identity, now=now)
        packets[instrument] = copy.deepcopy(packet)
    account_ids = {str(packet.get("account", {}).get("id") or "") for packet in packets.values()}
    if len(account_ids) != 1 or "" in account_ids:
        raise MultimarketEnvelopeError("account_divergent")
    if scanner.get("simultaneous_exposure_enabled") is not False:
        raise MultimarketEnvelopeError("simultaneous_exposure_enabled")
    packet_times = [_utc(packet.get("created_utc"), "packet_created") for packet in packets.values()]
    if any(abs((stamp - scanner_time).total_seconds()) > 300 for stamp in packet_times):
        raise MultimarketEnvelopeError("packet_scanner_timestamp_incompatible")
    canonical = json.dumps(
        {"scanner": scanner, "packets": packets}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "schema_version": ENVELOPE_SCHEMA,
        "envelope_id": "env-" + hashlib.sha256(canonical).hexdigest()[:16],
        "generated_utc": scanner.get("generated_utc"),
        "market_universe": copy.deepcopy(scanner),
        "packets_by_instrument": packets,
        "account": copy.deepcopy(packets["MNQ"]["account"]),
        "simultaneous_exposure_enabled": False,
    }
