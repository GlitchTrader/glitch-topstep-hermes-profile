"""Allowlisted public bundles for evaluation run persistence — no credentials in JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PUBLIC_BUNDLE_SCHEMA = "glitch.topstep.evaluation_run_public_bundle.v1"

RUN_TOP_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "run_id",
        "evaluation_only",
        "reason",
        "message",
        "production_parallelism",
        "cognitive_replay",
        "multi_envelope",
        "authorized_utc",
        "max_parallel_slots",
        "envelope_count",
        "session_cost_usd",
        "production_paths_untouched",
        "trail_a_gate",
        "metrics",
        "failed_at",
        "frame_id",
        "sealed_snapshot_hash",
        "sealed_envelope_hash",
        "envelope_hash",
        "sealed_validity_seconds",
        "frame_results",
        "frame_result",
        "profile_slots",
        "selection",
        "preflight",
    }
)

PROFILE_SLOT_KEYS = frozenset(
    {
        "profile_id",
        "invocation_id",
        "status",
        "artifact_path",
        "snapshot_hash",
        "envelope_hash",
        "normalized",
        "latency_ms",
        "cost_usd",
        "session_cost_usd",
        "estimated_cost_usd",
        "prompt_version",
        "profile_version",
        "schema_version",
        "model",
        "provider",
        "error_class",
        "reason",
    }
)

NORMALIZED_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "profile_id",
        "profile_version",
        "invocation_id",
        "envelope_id",
        "envelope_hash",
        "state",
        "comparability",
        "profile_declared_state",
        "profile_declared_direction",
        "capacity_gate_reason",
        "instrument",
        "direction",
        "thesis",
        "evidence_refs",
        "entry",
        "entry_range",
        "stop",
        "target",
        "target_absence_reason",
        "horizon_bars",
        "invalidation",
        "uncertainties",
        "forecast",
        "completeness_used",
        "raw_status",
        "error_code",
        "started_utc",
        "finished_utc",
        "latency_ms",
    }
)

SELECTION_KEYS = frozenset(
    {
        "outcome",
        "decision_code",
        "selected_profile_id",
        "decision_trace",
        "objections",
        "run_id",
        "envelope_id",
        "envelope_hash",
        "snapshot_hash",
        "instrument",
        "candidates_considered",
    }
)

FRAME_RESULT_KEYS = frozenset(
    {
        "status",
        "reason",
        "scenario_id",
        "frame_id",
        "sealed_snapshot_hash",
        "sealed_envelope_hash",
        "sealed_validity_seconds",
        "profile_slots",
        "selection",
        "identity_ok",
        "aggregator_ok",
        "session_cost_usd",
    }
)

PREFLIGHT_KEYS = frozenset({"verdict", "status", "run_id", "ready", "blocking", "checks"})
PREFLIGHT_CHECK_KEYS = frozenset({"id", "ok"})

FORBIDDEN_SUBSTRINGS = (
    "TEST_EVALUATION_SECRET",
    "TEST_API_KEY",
    "Authorization:",
    "Bearer ",
    "OPENROUTER_API_KEY",
    "EVALUATION_OPENROUTER_API_KEY",
)


def _pick(mapping: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    return {key: mapping[key] for key in allowed if key in mapping}


def _classify_error(reason: Any, status: Any) -> str | None:
    text = str(reason or status or "").lower()
    if not text:
        return None
    if "profile_error" in text or "provider" in text:
        return "provider_error"
    if "timeout" in text:
        return "timeout"
    if "incomplete" in text:
        return "profile_incomplete"
    if "cost_budget" in text:
        return "cost_budget_exceeded"
    if "mutation" in text:
        return "production_artifact_mutation"
    return "classified_failure"


def public_normalized(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    picked = _pick(value, NORMALIZED_KEYS)
    if "evidence_refs" in picked and isinstance(picked["evidence_refs"], list):
        picked["evidence_refs"] = [str(item) for item in picked["evidence_refs"]]
    if "uncertainties" in picked and isinstance(picked["uncertainties"], list):
        picked["uncertainties"] = [str(item) for item in picked["uncertainties"]]
    return picked or None


def public_selection(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    picked = _pick(value, SELECTION_KEYS)
    if "decision_trace" in picked and isinstance(picked["decision_trace"], list):
        picked["decision_trace"] = [str(item) for item in picked["decision_trace"]]
    if "objections" in picked and isinstance(picked["objections"], list):
        picked["objections"] = [str(item) for item in picked["objections"]]
    return picked or None


def public_preflight(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    picked = _pick(value, PREFLIGHT_KEYS)
    checks = value.get("checks")
    if isinstance(checks, list):
        picked["checks"] = [
            _pick(row, PREFLIGHT_CHECK_KEYS)
            for row in checks
            if isinstance(row, dict)
        ]
    blocking = value.get("blocking")
    if isinstance(blocking, list):
        picked["blocking"] = [str(item) for item in blocking]
    return picked or None


def public_profile_slot(row: dict[str, Any]) -> dict[str, Any]:
    """Build allowlisted slot from internal worker row or legacy/public slot."""
    if row.get("normalized") is not None and "artifact" not in row:
        base = _pick(row, PROFILE_SLOT_KEYS)
        norm = public_normalized(base.get("normalized"))
        if norm:
            base["normalized"] = norm
        return base

    art = row.get("artifact") if isinstance(row.get("artifact"), dict) else {}
    profile = art.get("profile") if isinstance(art.get("profile"), dict) else {}
    status = art.get("status") or row.get("status")
    out: dict[str, Any] = {
        "profile_id": row.get("profile_id"),
        "invocation_id": row.get("invocation_id") or art.get("invocation_id"),
        "status": status,
        "artifact_path": row.get("artifact_path"),
        "snapshot_hash": art.get("snapshot_hash_after") or art.get("snapshot_hash"),
        "envelope_hash": art.get("envelope_hash_after") or art.get("envelope_hash"),
        "normalized": public_normalized(art.get("normalized")),
        "latency_ms": art.get("latency_ms"),
        "cost_usd": art.get("cost_usd"),
        "session_cost_usd": art.get("session_cost_usd"),
        "prompt_version": profile.get("prompt_version") or art.get("prompt_version"),
        "profile_version": profile.get("profile_version") or art.get("profile_version"),
        "schema_version": art.get("schema_version"),
        "model": art.get("model"),
        "provider": art.get("provider"),
    }
    if status and status != "completed":
        out["error_class"] = _classify_error(art.get("reason") or art.get("error_code"), status)
        reason = art.get("reason") or art.get("error_code")
        if reason is not None:
            out["reason"] = str(reason)
    return {key: value for key, value in out.items() if value is not None}


def public_frame_result(frame: dict[str, Any]) -> dict[str, Any]:
    picked = _pick(frame, FRAME_RESULT_KEYS)
    slots = frame.get("profile_slots")
    if isinstance(slots, list):
        picked["profile_slots"] = [public_profile_slot(slot) for slot in slots if isinstance(slot, dict)]
    selection = public_selection(frame.get("selection"))
    if selection:
        picked["selection"] = selection
    return picked


def public_run_bundle(result: dict[str, Any]) -> dict[str, Any]:
    """Return allowlisted run summary safe for disk persistence."""
    out = _pick(result, RUN_TOP_KEYS)
    out["schema_version"] = str(result.get("schema_version") or PUBLIC_BUNDLE_SCHEMA)

    if isinstance(result.get("profile_slots"), list):
        out["profile_slots"] = [public_profile_slot(slot) for slot in result["profile_slots"] if isinstance(slot, dict)]

    if isinstance(result.get("frame_results"), list):
        out["frame_results"] = [public_frame_result(fr) for fr in result["frame_results"] if isinstance(fr, dict)]

    frame_result = result.get("frame_result")
    if isinstance(frame_result, dict):
        out["frame_result"] = public_frame_result(frame_result)

    selection = public_selection(result.get("selection"))
    if selection:
        out["selection"] = selection

    preflight = public_preflight(result.get("preflight"))
    if preflight:
        out["preflight"] = preflight

    metrics = result.get("metrics")
    if isinstance(metrics, dict):
        out["metrics"] = metrics

    trail_a_gate = result.get("trail_a_gate")
    if isinstance(trail_a_gate, dict):
        out["trail_a_gate"] = {str(k): str(v) for k, v in trail_a_gate.items()}

    return out


def persist_public_run_bundle(result: dict[str, Any], output: Path) -> dict[str, Any]:
    public = public_run_bundle(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    return public


def bundle_text_forbidden_sentinels(text: str, extra: tuple[str, ...] = ()) -> list[str]:
    hits: list[str] = []
    for needle in (*FORBIDDEN_SUBSTRINGS, *extra):
        if needle and needle in text:
            hits.append(needle)
    secret_like = re.findall(r"sk-or-[A-Za-z0-9]{8,}", text)
    hits.extend(secret_like)
    return hits


def slot_normalized(slot: dict[str, Any]) -> dict[str, Any] | None:
    norm = slot.get("normalized")
    if isinstance(norm, dict):
        return norm
    art = slot.get("artifact")
    if isinstance(art, dict) and isinstance(art.get("normalized"), dict):
        return art["normalized"]
    return None


def slot_replay_fields(slot: dict[str, Any]) -> dict[str, Any]:
    if slot.get("latency_ms") is not None or slot.get("cost_usd") is not None:
        return {
            "latency_ms": slot.get("latency_ms"),
            "cost_usd": slot.get("cost_usd"),
            "model": slot.get("model"),
            "provider": slot.get("provider"),
            "prompt_version": slot.get("prompt_version"),
            "profile_version": slot.get("profile_version"),
            "invocation_id": slot.get("invocation_id"),
            "status": slot.get("status"),
        }
    art = slot.get("artifact") if isinstance(slot.get("artifact"), dict) else {}
    profile = art.get("profile") if isinstance(art.get("profile"), dict) else {}
    return {
        "latency_ms": art.get("latency_ms"),
        "cost_usd": art.get("cost_usd"),
        "model": art.get("model"),
        "provider": art.get("provider"),
        "prompt_version": profile.get("prompt_version"),
        "profile_version": profile.get("profile_version"),
        "invocation_id": art.get("invocation_id") or slot.get("invocation_id"),
        "status": art.get("status"),
        "raw_profile_output": art.get("raw_profile_output"),
    }
