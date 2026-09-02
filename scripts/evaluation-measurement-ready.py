"""Evaluation-lane measurement readiness gate — offline only, never blocks trading."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import parse_utc, read_json, utc_now  # noqa: E402

RESULT_SCHEMA = "glitch.topstep.evaluation_measurement_ready.v1"
GATE_ID = "evaluation_measurement_ready"
BAR_LAG_MS_MAX = 120_000

_BAR_SPEC = importlib.util.spec_from_file_location("audit_bar", SCRIPTS / "audit-capture-bar-quality.py")
assert _BAR_SPEC and _BAR_SPEC.loader
_BAR = importlib.util.module_from_spec(_BAR_SPEC)
_BAR_SPEC.loader.exec_module(_BAR)


def _check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    ok: bool,
    reason: str,
    detail: Any = None,
) -> None:
    row: dict[str, Any] = {"id": check_id, "ok": ok, "reason": reason}
    if detail is not None:
        row["detail"] = detail
    checks.append(row)


def _daily_capture_locked(packet: dict[str, Any] | None) -> bool:
    if not packet:
        return False
    execution = packet.get("execution") if isinstance(packet.get("execution"), dict) else {}
    if execution.get("daily_capture_locked") is True:
        return True
    dc = packet.get("daily_capture") if isinstance(packet.get("daily_capture"), dict) else {}
    return dc.get("locked") is True


def _bar_issues(packet: dict[str, Any]) -> list[str]:
    audit = _BAR._bar_audit(packet)
    issues: list[str] = []
    if audit.get("timing_class") == "mid_bar_partial":
        issues.append("bar_1m_partial")
    mo = packet.get("market_observation") or {}
    obs = mo.get("observation") if isinstance(mo.get("observation"), dict) else {}
    lag_ms = None
    for tf in obs.get("timeframes") or []:
        if not isinstance(tf, dict) or tf.get("timeframe_minutes") != 1:
            continue
        if tf.get("latest_bar_partial") is True:
            issues.append("bar_1m_partial")
        latest = tf.get("latest_bar_utc")
        quote = (packet.get("market") or {}).get("quote_timestamp")
        if latest and quote:
            try:
                lag_ms = int(
                    (
                        parse_utc(str(quote).replace("+00:00", "Z"))
                        - parse_utc(str(latest).replace("+00:00", "Z"))
                    ).total_seconds()
                    * 1000
                )
            except (TypeError, ValueError):
                pass
    if lag_ms is not None and lag_ms > BAR_LAG_MS_MAX:
        issues.append("bar_1m_lag")
    if audit.get("state_complete") is False:
        issues.append("gateway_state_incomplete")
    return sorted(set(issues))


def _snapshot_expired(packet: dict[str, Any], decision: dict[str, Any] | None) -> bool:
    if not decision:
        return False
    intent = decision.get("intent") if isinstance(decision.get("intent"), dict) else {}
    expires = intent.get("expires_utc")
    recorded = decision.get("recorded_utc")
    if not expires or not recorded:
        return False
    try:
        return parse_utc(recorded) > parse_utc(expires)
    except (TypeError, ValueError):
        return False


def _capacity_ok(packet: dict[str, Any], *, profile_id: str = "baseline-current") -> tuple[bool, str]:
    try:
        cap_spec = importlib.util.spec_from_file_location("capability", SCRIPTS / "ensemble_capability.py")
        env_spec = importlib.util.spec_from_file_location("envelope", SCRIPTS / "ensemble_envelope.py")
        assert cap_spec and cap_spec.loader and env_spec and env_spec.loader
        cap_mod = importlib.util.module_from_spec(cap_spec)
        env_mod = importlib.util.module_from_spec(env_spec)
        cap_spec.loader.exec_module(cap_mod)
        env_spec.loader.exec_module(env_mod)
        matrix = read_json(REPO / "evaluation/capability-matrix.json")
        mapping = env_mod.load_packet_envelope_mapping()
        env = env_mod.build_evaluation_envelope(
            packet=packet,
            source_catalog=matrix["source_catalog"],
            reference_utc=str(packet.get("created_utc") or ""),
            frame_id=str(packet.get("packet_id") or ""),
            corpus_ref="measurement_ready",
            mapping=mapping,
        )
        gate = cap_mod.capacity_gate(env, profile_id, matrix)
        return bool(gate.get("allows_directional_evaluation")), str(gate.get("reason") or "capacity_gate")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return False, f"capacity_eval_error:{exc}"


def _evidence_chain_complete(
    *,
    packet: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
) -> tuple[bool, str]:
    missing: list[str] = []
    if not packet or not packet.get("packet_id"):
        missing.append("packet_id")
    if not decision:
        missing.append("decision")
    else:
        intent = decision.get("intent") if isinstance(decision.get("intent"), dict) else {}
        if not intent.get("intent_id"):
            missing.append("intent_id")
        if not intent.get("snapshot_hash") and not decision.get("snapshot_hash"):
            missing.append("snapshot_hash")
        if packet and intent.get("packet_id") and intent.get("packet_id") != packet.get("packet_id"):
            return False, "packet_id_mismatch_intent"
        if packet and decision.get("packet_id") and decision.get("packet_id") != packet.get("packet_id"):
            return False, "packet_id_mismatch_decision"
    if not receipt:
        missing.append("receipt")
    else:
        if decision:
            intent = decision.get("intent") or {}
            rid = receipt.get("intent_id")
            if rid and intent.get("intent_id") and rid != intent.get("intent_id"):
                return False, "intent_id_mismatch_receipt"
            rpid = receipt.get("packet_id")
            if rpid and packet and rpid != packet.get("packet_id"):
                return False, "packet_id_mismatch_receipt"
    if missing:
        return False, f"missing:{','.join(missing)}"
    return True, "complete"


def _maintenance_window(health: dict[str, Any] | None) -> bool:
    if not health:
        return False
    if health.get("status") == "degraded":
        return True
    recovery = health.get("recovery") if isinstance(health.get("recovery"), dict) else {}
    if recovery.get("active") is True:
        return True
    lifecycle = health.get("lifecycle") if isinstance(health.get("lifecycle"), dict) else {}
    if str(lifecycle.get("state") or "").lower() not in {"", "ready", "armed"}:
        return True
    dq = health.get("data_quality") if isinstance(health.get("data_quality"), dict) else {}
    if dq.get("state_complete") is False:
        return True
    return False


def _market_valid(packet: dict[str, Any] | None, health: dict[str, Any] | None) -> tuple[bool, str]:
    if health:
        dq = health.get("data_quality") if isinstance(health.get("data_quality"), dict) else {}
        op = dq.get("operational") if isinstance(dq.get("operational"), dict) else {}
        for stream_key in ("marketStream", "userStream"):
            stream = op.get(stream_key) if isinstance(op.get(stream_key), dict) else {}
            if stream and str(stream.get("state") or "").lower() != "connected":
                return False, f"{stream_key}_not_connected"
        recon = op.get("reconciliation") if isinstance(op.get("reconciliation"), dict) else {}
        if recon and str(recon.get("state") or "").lower() not in {"", "succeeded"}:
            return False, "reconciliation_not_succeeded"
    if packet:
        market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
        if market.get("quote_valid") is False:
            return False, "quote_invalid"
        instrument = packet.get("instrument") or market.get("instrument")
        if not instrument:
            return False, "instrument_missing"
    if not packet and not health:
        return False, "no_packet_or_health"
    return True, "ok"


def evaluation_measurement_ready(
    *,
    mode: str = "capture",
    packet: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    gateway_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return machine-readable readiness verdict for evaluation capture."""
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []

    if mode not in {"preflight", "capture"}:
        mode = "capture"

    if _maintenance_window(gateway_health):
        _check(checks, check_id="maintenance_window", ok=False, reason="gateway_degraded_or_recovery_active")
        blocking.append("maintenance_window")
    else:
        _check(checks, check_id="maintenance_window", ok=True, reason="no_maintenance_signal")

    market_ok, market_detail = _market_valid(packet, gateway_health)
    if not market_ok:
        _check(checks, check_id="market_not_valid", ok=False, reason=market_detail)
        blocking.append("market_not_valid")
    else:
        _check(checks, check_id="market_not_valid", ok=True, reason=market_detail)

    gh_sc = None
    if gateway_health:
        dq = gateway_health.get("data_quality") if isinstance(gateway_health.get("data_quality"), dict) else {}
        gh_sc = dq.get("state_complete")
        if gh_sc is False:
            _check(checks, check_id="gateway_state_incomplete", ok=False, reason="health_state_complete_false")
            blocking.append("gateway_state_incomplete")
        else:
            _check(checks, check_id="gateway_state_incomplete", ok=True, reason="health_state_complete")

    if mode == "preflight":
        return {
            "schema_version": RESULT_SCHEMA,
            "gate": GATE_ID,
            "recorded_utc": utc_now(),
            "mode": mode,
            "ready": len(blocking) == 0,
            "blocking_reasons": blocking,
            "checks": checks,
        }

    if packet is None:
        _check(checks, check_id="evidence_chain_incomplete", ok=False, reason="packet_required_for_capture_mode")
        blocking.append("evidence_chain_incomplete")
    else:
        if _daily_capture_locked(packet):
            _check(checks, check_id="daily_capture_locked", ok=False, reason="execution_daily_capture_locked")
            blocking.append("daily_capture_locked")
        else:
            _check(checks, check_id="daily_capture_locked", ok=True, reason="not_locked")

        bar_issues = _bar_issues(packet)
        if "bar_1m_partial" in bar_issues:
            _check(checks, check_id="bar_1m_partial", ok=False, reason="partial_1m_bar")
            blocking.append("bar_1m_partial")
        else:
            _check(checks, check_id="bar_1m_partial", ok=True, reason="bar_complete_or_absent")

        if "bar_1m_lag" in bar_issues:
            _check(checks, check_id="bar_1m_lag", ok=False, reason=f"lag_over_{BAR_LAG_MS_MAX}ms")
            blocking.append("bar_1m_lag")
        else:
            _check(checks, check_id="bar_1m_lag", ok=True, reason="within_lag_budget")

        if "gateway_state_incomplete" in bar_issues and "gateway_state_incomplete" not in blocking:
            _check(checks, check_id="gateway_state_incomplete", ok=False, reason="packet_state_complete_false")
            blocking.append("gateway_state_incomplete")
        elif gh_sc is not False and "gateway_state_incomplete" not in blocking:
            _check(checks, check_id="gateway_state_incomplete", ok=True, reason="packet_state_complete")

        if _snapshot_expired(packet, decision):
            _check(checks, check_id="snapshot_expired", ok=False, reason="decision_after_intent_expiry")
            blocking.append("snapshot_expired")
        else:
            _check(checks, check_id="snapshot_expired", ok=True, reason="within_intent_expiry")

        cap_ok, cap_reason = _capacity_ok(packet)
        if not cap_ok:
            _check(checks, check_id="insufficient_instrument_capacity", ok=False, reason=cap_reason)
            blocking.append("insufficient_instrument_capacity")
        else:
            _check(checks, check_id="insufficient_instrument_capacity", ok=True, reason=cap_reason)

        chain_ok, chain_reason = _evidence_chain_complete(packet=packet, decision=decision, receipt=receipt)
        if not chain_ok:
            _check(checks, check_id="evidence_chain_incomplete", ok=False, reason=chain_reason)
            blocking.append("evidence_chain_incomplete")
        else:
            _check(checks, check_id="evidence_chain_incomplete", ok=True, reason=chain_reason)

    return {
        "schema_version": RESULT_SCHEMA,
        "gate": GATE_ID,
        "recorded_utc": utc_now(),
        "mode": mode,
        "ready": len(blocking) == 0,
        "blocking_reasons": sorted(set(blocking)),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluation measurement readiness gate (offline)")
    parser.add_argument("--mode", choices=("preflight", "capture"), default="capture")
    parser.add_argument("--packet", type=Path, help="Packet JSON file or minute-frame with packet key")
    parser.add_argument("--decision", type=Path, help="Single decision record JSON")
    parser.add_argument("--receipt", type=Path, help="Single receipt JSON")
    parser.add_argument("--gateway-health", type=Path, help="Gateway health snapshot JSON")
    parser.add_argument("--output", type=Path, help="Write result JSON")
    args = parser.parse_args()

    def _load_obj(path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.is_file():
            return None
        doc = read_json(path)
        if isinstance(doc.get("packet"), dict):
            return doc["packet"]
        return doc if isinstance(doc, dict) else None

    packet = _load_obj(args.packet)
    decision = read_json(args.decision) if args.decision and args.decision.is_file() else None
    receipt = read_json(args.receipt) if args.receipt and args.receipt.is_file() else None
    health = read_json(args.gateway_health) if args.gateway_health and args.gateway_health.is_file() else None

    result = evaluation_measurement_ready(
        mode=args.mode,
        packet=packet,
        decision=decision,
        receipt=receipt,
        gateway_health=health,
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
