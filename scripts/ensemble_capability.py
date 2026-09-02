"""Capability gate for ensemble profiles."""

from __future__ import annotations

from typing import Any


def profile_spec(matrix: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profiles = matrix.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("capability_matrix_profiles_missing")
    spec = profiles.get(profile_id)
    if not isinstance(spec, dict):
        raise ValueError(f"profile_not_in_matrix:{profile_id}")
    return spec


def effective_completeness(
    envelope: dict[str, Any],
    profile_id: str,
    matrix: dict[str, Any],
) -> dict[str, str]:
    spec = profile_spec(matrix, profile_id)
    completeness = envelope.get("completeness")
    if not isinstance(completeness, dict):
        raise ValueError("envelope_completeness_missing")
    required = [str(item) for item in spec.get("required_sources", [])]
    optional = [str(item) for item in spec.get("optional_sources", [])]
    used: dict[str, str] = {}
    for source_id in sorted(set(required) | set(optional)):
        state = str(completeness.get(source_id) or "missing_required")
        if source_id in optional and source_id not in required and source_id not in completeness:
            state = "not_applicable"
        used[source_id] = state
    return used


def capacity_gate(
    envelope: dict[str, Any],
    profile_id: str,
    matrix: dict[str, Any],
) -> dict[str, Any]:
    spec = profile_spec(matrix, profile_id)
    used = effective_completeness(envelope, profile_id, matrix)
    required = [str(item) for item in spec.get("required_sources", [])]
    missing = [
        source_id
        for source_id in required
        if used.get(source_id) in {None, "", "missing_required"}
    ]
    stale_or_bad = [
        source_id
        for source_id in required
        if used.get(source_id) in {"stale", "inconsistent"}
    ]
    comparable = not missing and not stale_or_bad
    return {
        "profile_id": profile_id,
        "completeness_used": used,
        "missing_required": missing,
        "stale_or_inconsistent": stale_or_bad,
        "comparable": comparable,
        "allows_directional_evaluation": comparable,
    }
