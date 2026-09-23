"""Lightweight validators for ensemble v1 schemas (no external jsonschema dependency).

Structural checks run first; semantic validators (formerly ensemble_semantic)
follow and enforce cross-field / control-plane consistency.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ensemble_envelope import ENVELOPE_SCHEMA, envelope_hash
from ensemble_geometry import validate_entry_candidate_geometry

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
DIRECTIONAL_STATES = frozenset({"candidate", "held"})

PROFILE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROFILE_ROOT / "skills"


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


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def validate_capability_matrix_semantic(matrix: dict[str, Any]) -> None:
    catalog = matrix.get("source_catalog")
    profiles = matrix.get("profiles")
    if not isinstance(catalog, dict) or not isinstance(profiles, dict):
        raise ValueError("matrix_catalog_or_profiles_invalid")
    catalog_ids = set(catalog)
    for profile_id, spec in profiles.items():
        if not isinstance(spec, dict):
            raise ValueError(f"profile_spec_invalid:{profile_id}")
        required = [str(x) for x in spec.get("required_sources", [])]
        optional = [str(x) for x in spec.get("optional_sources", [])]
        overlap = set(required) & set(optional)
        if overlap:
            raise ValueError(f"required_optional_overlap:{profile_id}:{sorted(overlap)}")
        for source_id in required + optional:
            if source_id not in catalog_ids:
                raise ValueError(f"unknown_source:{profile_id}:{source_id}")
        for skill in spec.get("skills", []):
            skill_name = str(skill)
            if not (SKILLS_ROOT / skill_name).is_dir():
                raise ValueError(f"unknown_skill:{profile_id}:{skill_name}")
        horizon = spec.get("horizon_bars")
        if not isinstance(horizon, dict):
            raise ValueError(f"horizon_bars_required:{profile_id}")
        if int(horizon.get("min", 0)) <= 0 or int(horizon.get("max", 0)) < int(horizon.get("min", 0)):
            raise ValueError(f"horizon_bars_invalid:{profile_id}")


def validate_registry_semantic(
    registry: dict[str, Any],
    *,
    matrix_version: str,
    config_version: str,
    rules_version: str,
) -> None:
    if registry.get("capability_matrix_version") != matrix_version:
        raise ValueError("registry_matrix_version_mismatch")
    if registry.get("config_version") != config_version:
        raise ValueError("registry_config_version_mismatch")
    if registry.get("aggregator_rules_version") != rules_version:
        raise ValueError("registry_rules_version_mismatch")
    if registry.get("promotion_status") != "blocked":
        raise ValueError("registry_promotion_must_be_blocked_in_v1")
    kinds = {str(row.get("profile_kind")) for row in registry.get("profiles", [])}
    if "baseline" not in kinds:
        raise ValueError("registry_missing_baseline_kind")


def validate_config_semantic(config: dict[str, Any], *, profile_count: int) -> None:
    budget = config.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("config_budget_missing")
    per = int(budget.get("per_profile_timeout_ms", 0))
    total = int(budget.get("total_timeout_ms", 0))
    agg = int(budget.get("aggregation_budget_ms", 0))
    slots = int(budget.get("max_parallel_slots", 1))
    if slots < 1 or slots > 2:
        raise ValueError("evaluation_parallel_slots_must_be_1_or_2")
    worst_case = math.ceil(profile_count / slots) * per + agg
    if worst_case > total:
        raise ValueError("config_timeout_inconsistent")
    semantics = config.get("promotion_threshold_semantics")
    if not isinstance(semantics, dict) or not semantics:
        raise ValueError("promotion_threshold_semantics_required")


def validate_aggregator_rules_semantic(rules: dict[str, Any]) -> None:
    normalization = rules.get("critical_normalization")
    if not isinstance(normalization, dict):
        raise ValueError("critical_normalization_required")
    no_rule = normalization.get("no_objective_rule_match")
    if not isinstance(no_rule, dict):
        raise ValueError("critical_normalization_no_rule_required")
    if no_rule.get("action") != "normalize_to_warning":
        raise ValueError("critical_normalization_action_invalid")
    if not str(no_rule.get("decision_code") or "").strip():
        raise ValueError("critical_normalization_decision_code_required")

    equivalence = rules.get("candidate_equivalence")
    if not isinstance(equivalence, dict):
        raise ValueError("candidate_equivalence_required")
    group_by = equivalence.get("group_by")
    if not isinstance(group_by, list) or "contract_id" not in group_by:
        raise ValueError("equivalence_group_by_incomplete")
    tolerances = equivalence.get("tick_tolerance_by_instrument")
    if not isinstance(tolerances, dict) or "DEFAULT" not in tolerances:
        raise ValueError("equivalence_tick_tolerance_required")

    for rule in rules.get("objective_elimination_rules", []):
        if not isinstance(rule, dict):
            continue
        if rule.get("validator") == "validate_protective_amendment_geometry":
            raise ValueError("protective_amendment_validator_forbidden_for_entries")


def validate_envelope_semantic(envelope: dict[str, Any], mapping: dict[str, Any]) -> None:
    accepted = mapping.get("accepted_packet_schema_versions", [])
    packet_version = str(envelope.get("packet_schema_version") or "")
    if packet_version and packet_version not in accepted:
        raise ValueError("packet_schema_version_not_accepted")
    packet = envelope.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("envelope_packet_missing")
    for prohibited in mapping.get("prohibited_packet_fields", []):
        if prohibited in packet:
            raise ValueError(f"prohibited_packet_field:{prohibited}")
    instrument = str(envelope.get("instrument") or "").upper()
    packet_instrument = str(packet.get("instrument") or "").upper()
    if packet_instrument and instrument != packet_instrument:
        raise ValueError("envelope_instrument_mismatch")
    # envelope_hash is a computed property; candidates must match at validation time
    _ = envelope_hash(envelope)


def validate_candidate_semantic(
    candidate: dict[str, Any],
    *,
    envelope: dict[str, Any],
) -> None:
    state = str(candidate.get("state") or "")
    direction = candidate.get("direction")
    started = _parse_utc(str(candidate["started_utc"]))
    finished = _parse_utc(str(candidate["finished_utc"]))
    if finished < started:
        raise ValueError("candidate_finished_before_started")
    latency = int(candidate.get("latency_ms") or 0)
    observed_ms = int((finished - started).total_seconds() * 1000)
    if latency > observed_ms + 1000:
        raise ValueError("candidate_latency_inconsistent")

    if candidate.get("instrument") != envelope.get("instrument"):
        raise ValueError("candidate_instrument_mismatch")

    envelope_contract = envelope.get("contract") if isinstance(envelope.get("contract"), dict) else {}
    expected_contract_id = envelope.get("contract_id") or envelope_contract.get("contract_id") or envelope_contract.get("id")
    if expected_contract_id is not None and candidate.get("contract_id") != expected_contract_id:
        raise ValueError("candidate_contract_mismatch")
    expected_generation = envelope.get("contract_generation") or envelope_contract.get("contract_generation") or envelope_contract.get("generation")
    if expected_generation is not None and candidate.get("contract_generation") != expected_generation:
        raise ValueError("candidate_contract_generation_mismatch")
    if str(candidate.get("envelope_hash") or "") != envelope_hash(envelope):
        raise ValueError("candidate_envelope_hash_mismatch")

    entry_range = candidate.get("entry_range")
    if isinstance(entry_range, dict):
        low = entry_range.get("low")
        high = entry_range.get("high")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)) and float(low) > float(high):
            raise ValueError("candidate_entry_range_inverted")

    if (
        state in DIRECTIONAL_STATES
        and direction in {"long", "short"}
        and state != "missing_required_evidence"
        and str(candidate.get("comparability") or "") == "comparable"
    ):
        stop = candidate.get("stop")
        if stop is None:
            raise ValueError("directional_candidate_stop_required")
        target = candidate.get("target")
        if target is None and not candidate.get("target_absence_reason"):
            raise ValueError("directional_candidate_target_or_reason_required")
        from ensemble_geometry import reference_price_from_envelope

        ref_price = reference_price_from_envelope(envelope)
        codes = validate_entry_candidate_geometry(
            direction=str(direction),
            entry=_as_float(candidate.get("entry")),
            entry_range=entry_range if isinstance(entry_range, dict) else None,
            stop=_as_float(stop),
            target=_as_float(target),
            reference_price=ref_price,
        )
        if codes:
            raise ValueError(f"candidate_geometry_invalid:{','.join(codes)}")

    if state == "missing_required_evidence":
        if str(candidate.get("comparability") or "") != "not_comparable":
            raise ValueError("missing_required_must_be_not_comparable")
