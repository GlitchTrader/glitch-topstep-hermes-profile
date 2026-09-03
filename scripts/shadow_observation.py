"""Shared shadow observation record builder — evaluation lane, zero operational writes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

OBSERVATION_OFFLINE_SCHEMA = "glitch.topstep.shadow_observation_offline.v1"
OBSERVATION_LIVE_SCHEMA = "glitch.topstep.shadow_observation.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def snapshot_age_ms(envelope: dict[str, Any]) -> int | None:
    ref = str(envelope.get("reference_utc") or "")
    if not ref:
        return None
    try:
        ref_dt = datetime.fromisoformat(ref.replace("Z", "+00:00")).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, int((now - ref_dt).total_seconds() * 1000))
    except ValueError:
        return None


def build_shadow_observation(
    *,
    run_id: str,
    envelope: dict[str, Any],
    profile_decisions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    selection: dict[str, Any],
    baseline_id: str,
    cost_usd: float,
    latency_ms_total: int,
    shadow_live: bool,
    schema_version: str = OBSERVATION_OFFLINE_SCHEMA,
    isolation_audit: list[dict[str, Any]] | None = None,
    operational_writes_detected: bool = False,
    gateway_touched: bool = False,
    profile_source: str = "fixtures",
) -> dict[str, Any]:
    baseline_decision = next((d for d in profile_decisions if d.get("is_baseline")), None)
    pool_states = {"candidate", "held"}
    non_selected = [
        {
            "profile_id": c.get("profile_id"),
            "state": c.get("state"),
            "direction": c.get("direction"),
            "reason": "not_selected_by_aggregator",
        }
        for c in candidates
        if str(c.get("state") or "") in pool_states
        and str(c.get("profile_id") or "") != str(selection.get("selected_profile_id") or "")
    ]

    base_dir = (baseline_decision or {}).get("direction")
    divergences: list[dict[str, Any]] = []
    for d in profile_decisions:
        if d.get("is_baseline") or not d.get("direction"):
            continue
        if base_dir and d.get("direction") not in {base_dir, "flat", "hold"}:
            divergences.append(
                {
                    "profile_id": d["profile_id"],
                    "baseline_direction": base_dir,
                    "profile_direction": d.get("direction"),
                    "kind": "direction_divergence",
                }
            )

    isolation_failures = [
        row
        for row in (isolation_audit or [])
        if not row.get("hermes_home_isolated") or row.get("profile_outside_evaluation_home")
    ]

    return {
        "schema_version": schema_version,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "evaluation_only": True,
        "shadow_live": shadow_live,
        "profile_source": profile_source,
        "intents_sent": 0,
        "orders_sent": 0,
        "writes_operacionais": 1 if operational_writes_detected else 0,
        "gateway_touched": gateway_touched,
        "envelope": {
            "envelope_id": envelope.get("envelope_id"),
            "snapshot_hash": envelope.get("snapshot_hash"),
            "envelope_hash": envelope.get("envelope_hash"),
            "snapshot_age_ms": snapshot_age_ms(envelope),
            "completeness": envelope.get("completeness"),
        },
        "profile_decisions": profile_decisions,
        "candidates": [
            {
                "profile_id": c.get("profile_id"),
                "invocation_id": c.get("invocation_id"),
                "state": c.get("state"),
                "direction": c.get("direction"),
                "comparability": c.get("comparability"),
            }
            for c in candidates
        ],
        "aggregator_selection": {
            "outcome": selection.get("outcome"),
            "decision_code": selection.get("decision_code"),
            "selected_profile_id": selection.get("selected_profile_id"),
            "decision_trace": selection.get("decision_trace"),
            "no_selection_reason": selection.get("decision_code")
            if selection.get("outcome") == "no_selection"
            else None,
        },
        "baseline_comparison": {
            "baseline_profile_id": baseline_id,
            "baseline_state": (baseline_decision or {}).get("state"),
            "baseline_direction": base_dir,
            "matches_global_selection": str(selection.get("selected_profile_id") or "") == baseline_id,
        },
        "counterfactual": {
            "non_selected_candidates": non_selected,
            "diagnostic_only": selection.get("outcome") != "selected",
        },
        "cost_usd": round(cost_usd, 6),
        "latency_ms_total": latency_ms_total,
        "divergences": divergences,
        "isolation_audit": isolation_audit or [],
        "isolation_failures": isolation_failures,
    }
