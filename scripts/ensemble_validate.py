"""Lightweight validators for ensemble v1 schemas (no external jsonschema dependency)."""

from __future__ import annotations

from typing import Any

from ensemble_envelope import ENVELOPE_SCHEMA

CANDIDATE_SCHEMA = "glitch.topstep.normalized_candidate.v1"
SELECTION_SCHEMA = "glitch.topstep.ensemble_selection.v1"
MATRIX_SCHEMA = "glitch.topstep.profile_capability_matrix.v1"
REGISTRY_SCHEMA = "glitch.topstep.ensemble_registry.v1"
CONFIG_SCHEMA = "glitch.topstep.ensemble_config.v1"
RULES_SCHEMA = "glitch.topstep.aggregator_rules.v1"

CANDIDATE_STATES = frozenset({
    "candidate",
    "held",
    "no_edge",
    "missing_required_evidence",
    "data_quality_insufficient",
    "expired",
    "timeout",
    "error",
    "invalid",
})

SELECTION_OUTCOMES = frozenset({"selected", "no_selection", "classified_failure"})
PROFILE_KINDS = frozenset({"baseline", "directional", "reviewer", "observer"})


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_required")
    return value


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field}_must_be_object")
    return value


def validate_evaluation_envelope(value: dict[str, Any]) -> None:
    if value.get("schema_version") != ENVELOPE_SCHEMA:
        raise ValueError("evaluation_envelope_schema_version")
    for field in (
        "envelope_id",
        "snapshot_id",
        "snapshot_hash",
        "reference_utc",
        "valid_until_utc",
        "instrument",
        "packet_schema_version",
    ):
        _require_str(value.get(field), field)
    _require_dict(value.get("contract"), "contract")
    _require_dict(value.get("packet"), "packet")
    completeness = _require_dict(value.get("completeness"), "completeness")
    for state in completeness.values():
        if str(state) not in {
            "available",
            "stale",
            "partial",
            "inconsistent",
            "not_applicable",
            "missing_required",
        }:
            raise ValueError("completeness_state_invalid")
    _require_dict(value.get("source_refs"), "source_refs")


def validate_capability_matrix(value: dict[str, Any]) -> None:
    if value.get("schema_version") != MATRIX_SCHEMA:
        raise ValueError("capability_matrix_schema_version")
    _require_str(value.get("matrix_version"), "matrix_version")
    profiles = _require_dict(value.get("profiles"), "profiles")
    if not profiles:
        raise ValueError("profiles_empty")


def validate_registry(value: dict[str, Any]) -> None:
    if value.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError("registry_schema_version")
    _require_str(value.get("registry_version"), "registry_version")
    if value.get("evaluation_only") is not True:
        raise ValueError("registry_evaluation_only_required")
    for field in (
        "promotion_status",
        "execution_mode",
        "storage_root",
        "runner",
        "baseline_policy",
        "capability_matrix_version",
        "envelope_schema",
        "candidate_schema",
        "selection_schema",
        "aggregator_rules_version",
        "config_version",
    ):
        _require_str(value.get(field), field)
    profiles = value.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("registry_profiles_required")
    for row in profiles:
        if not isinstance(row, dict):
            raise ValueError("registry_profile_invalid")
        _require_str(row.get("profile_id"), "profile_id")
        _require_str(row.get("profile_version"), "profile_version")
        kind = _require_str(row.get("profile_kind"), "profile_kind")
        if kind not in PROFILE_KINDS:
            raise ValueError("registry_profile_kind_invalid")


def validate_ensemble_config(value: dict[str, Any]) -> None:
    if value.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError("ensemble_config_schema_version")
    _require_str(value.get("config_version"), "config_version")
    budget = _require_dict(value.get("budget"), "budget")
    for field in (
        "per_profile_timeout_ms",
        "total_timeout_ms",
        "aggregation_budget_ms",
        "max_parallel_slots",
    ):
        if field not in budget:
            raise ValueError(f"config_budget_{field}_required")
    _require_dict(value.get("timeout_policy"), "timeout_policy")
    _require_dict(value.get("promotion_threshold_semantics"), "promotion_threshold_semantics")


def validate_aggregator_rules(value: dict[str, Any]) -> None:
    if value.get("schema_version") != RULES_SCHEMA:
        raise ValueError("aggregator_rules_schema_version")
    _require_str(value.get("rules_version"), "rules_version")
    _require_dict(value.get("critical_normalization"), "critical_normalization")
    _require_dict(value.get("candidate_equivalence"), "candidate_equivalence")
    if not isinstance(value.get("objective_elimination_rules"), list):
        raise ValueError("objective_elimination_rules_required")


def validate_normalized_candidate(value: dict[str, Any]) -> None:
    if value.get("schema_version") != CANDIDATE_SCHEMA:
        raise ValueError("normalized_candidate_schema_version")
    state = _require_str(value.get("state"), "state")
    if state not in CANDIDATE_STATES:
        raise ValueError("candidate_state_invalid")
    comparability = _require_str(value.get("comparability"), "comparability")
    if comparability not in {"comparable", "not_comparable"}:
        raise ValueError("candidate_comparability_invalid")
    for field in (
        "run_id",
        "profile_id",
        "profile_version",
        "invocation_id",
        "envelope_id",
        "envelope_hash",
        "instrument",
        "started_utc",
        "finished_utc",
    ):
        _require_str(value.get(field), field)
    if not isinstance(value.get("latency_ms"), int) or value["latency_ms"] < 0:
        raise ValueError("latency_ms_invalid")
    _require_dict(value.get("completeness_used"), "completeness_used")


def validate_ensemble_selection(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SELECTION_SCHEMA:
        raise ValueError("ensemble_selection_schema_version")
    outcome = _require_str(value.get("outcome"), "outcome")
    if outcome not in SELECTION_OUTCOMES:
        raise ValueError("selection_outcome_invalid")
    if value.get("evaluation_only") is not True:
        raise ValueError("evaluation_only_required")
    if value.get("armed_promotion_allowed") is not False:
        raise ValueError("armed_promotion_forbidden")
    if not isinstance(value.get("decision_trace"), list):
        raise ValueError("decision_trace_required")
