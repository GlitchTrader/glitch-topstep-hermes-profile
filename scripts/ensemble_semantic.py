"""Semantic validators for ensemble v1 control-plane and candidates."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ensemble_envelope import envelope_hash
from ensemble_geometry import validate_entry_candidate_geometry

PROFILE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROFILE_ROOT / "skills"

DIRECTIONAL_STATES = frozenset({"candidate", "held"})


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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
    expected_hash = envelope_hash(envelope)
    # envelope_hash is computed property; candidates must match at validation time


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

    if str(candidate.get("instrument") or "").upper() != str(envelope.get("instrument") or "").upper():
        raise ValueError("candidate_instrument_mismatch")
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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None
