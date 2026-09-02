"""Adapt Hermes evaluation replay output to normalized_candidate contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import read_json

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "evaluation_output_contract.v1.json"
DIRECTIONAL_STATES = frozenset({"candidate", "held"})
ABSTENTION_DIRECTIONS = frozenset({"flat", "hold"})
DIRECTIONAL_DIRECTIONS = frozenset({"long", "short"})


def load_output_contract(path: Path | None = None) -> dict[str, Any]:
    return read_json(path or CONTRACT_PATH)


def _serialize_declared(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def classify_raw_output(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "category": "parsing_error",
            "subtype": "raw_not_object",
            "issues": ["raw_not_object"],
        }

    issues: list[str] = []
    state_raw = raw.get("state")
    direction_raw = raw.get("direction")
    action_raw = raw.get("action")

    if isinstance(state_raw, dict):
        return {
            "category": "contract_violation",
            "subtype": "state_field_contains_snapshot",
            "issues": ["state_field_is_object"],
            "state_raw_type": "object",
        }
    if isinstance(state_raw, list):
        return {
            "category": "parsing_error",
            "subtype": "state_field_is_array",
            "issues": ["state_field_is_array"],
        }

    state_text = str(state_raw or "").strip()
    if not state_text:
        issues.append("missing_state")

    direction_text = str(direction_raw or "").strip()
    if direction_text.upper() in {"BEARISH", "BULLISH", "NEUTRAL"}:
        issues.append("ambiguous_direction_vocabulary")

    if state_text.lower() in {"frozen", "active", "idle"}:
        issues.append("ambiguous_state_vocabulary")

    if action_raw is not None and str(action_raw).upper() == "NOTHING" and not state_text:
        issues.append("action_without_canonical_state")

    required_fields = ("thesis",)
    for field in required_fields:
        if not str(raw.get(field) or "").strip():
            issues.append(f"missing_{field}")

    if issues:
        category = "incomplete_output"
        if any(
            code in issues
            for code in (
                "ambiguous_direction_vocabulary",
                "ambiguous_state_vocabulary",
            )
        ):
            category = "ambiguous_output"
        return {
            "category": category,
            "subtype": issues[0],
            "issues": issues,
            "state_raw_type": "string" if state_text else "missing",
        }

    return {
        "category": "semantic_alias_candidate",
        "subtype": "explicit_fields_present",
        "issues": [],
        "state_raw_type": "string",
    }


def _canonical_state(state_raw: Any, contract: dict[str, Any]) -> str | None:
    if state_raw is None:
        return None
    if isinstance(state_raw, dict):
        return None
    text = str(state_raw).strip()
    if not text:
        return None
    canonical = set(contract.get("canonical_state_enum") or [])
    if text in canonical:
        return text
    aliases = contract.get("approved_state_aliases") or {}
    mapped = aliases.get(text) or aliases.get(text.upper())
    if mapped in canonical:
        return str(mapped)
    return None


def _canonical_direction(direction_raw: Any, contract: dict[str, Any]) -> str | None:
    if direction_raw is None:
        return None
    text = str(direction_raw).strip()
    if not text:
        return None
    canonical = set(contract.get("canonical_direction_enum") or [])
    lowered = text.lower()
    if lowered in canonical:
        return lowered
    aliases = contract.get("approved_direction_aliases") or {}
    mapped = aliases.get(text) or aliases.get(text.upper())
    if mapped in canonical:
        return str(mapped)
    return None


def _has_directional_geometry(raw: dict[str, Any]) -> bool:
    stop = raw.get("stop")
    entry = raw.get("entry")
    entry_range = raw.get("entry_range")
    if isinstance(stop, (int, float)) and (
        isinstance(entry, (int, float)) or isinstance(entry_range, dict)
    ):
        return True
    return False


def adapt_evaluation_output(
    *,
    raw: dict[str, Any] | None,
    gate: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract_doc = contract or load_output_contract()
    classification = classify_raw_output(raw)
    fixture = raw or {}
    declared_state = _serialize_declared(fixture.get("state"))
    declared_direction = fixture.get("direction")

    if gate.get("missing_required") or gate.get("stale_or_inconsistent"):
        return {
            "state": "missing_required_evidence",
            "comparability": "not_comparable",
            "profile_declared_state": declared_state,
            "profile_declared_direction": declared_direction,
            "capacity_gate_reason": (
                "missing_required"
                if gate.get("missing_required")
                else "stale_or_inconsistent"
            ),
            "direction": _canonical_direction(declared_direction, contract_doc),
            "error_code": None,
            "raw_status": None,
            "adapter_classification": classification,
        }

    comparable = bool(gate.get("comparable"))
    category = str(classification.get("category") or "")

    if category in {"contract_violation", "parsing_error", "ambiguous_output", "incomplete_output"}:
        return {
            "state": "invalid",
            "comparability": "comparable" if comparable else "not_comparable",
            "profile_declared_state": declared_state,
            "profile_declared_direction": declared_direction,
            "capacity_gate_reason": None,
            "direction": _canonical_direction(declared_direction, contract_doc),
            "error_code": classification.get("subtype"),
            "raw_status": category,
            "adapter_classification": classification,
        }

    mapped_state = _canonical_state(fixture.get("state"), contract_doc)
    mapped_direction = _canonical_direction(fixture.get("direction"), contract_doc)

    if mapped_state is None or mapped_direction is None:
        return {
            "state": "invalid",
            "comparability": "comparable" if comparable else "not_comparable",
            "profile_declared_state": declared_state,
            "profile_declared_direction": declared_direction,
            "capacity_gate_reason": None,
            "direction": mapped_direction,
            "error_code": "unapproved_vocabulary",
            "raw_status": "semantic_alias_rejected",
            "adapter_classification": classification,
        }

    if mapped_state in DIRECTIONAL_STATES:
        if mapped_direction in ABSTENTION_DIRECTIONS:
            return {
                "state": "invalid",
                "comparability": "comparable" if comparable else "not_comparable",
                "profile_declared_state": declared_state,
                "profile_declared_direction": declared_direction,
                "capacity_gate_reason": None,
                "direction": mapped_direction,
                "error_code": "candidate_direction_flat_conflict",
                "raw_status": "candidate_direction_flat_conflict",
                "adapter_classification": classification,
            }
        if mapped_direction not in DIRECTIONAL_DIRECTIONS:
            return {
                "state": "invalid",
                "comparability": "comparable" if comparable else "not_comparable",
                "profile_declared_state": declared_state,
                "profile_declared_direction": declared_direction,
                "capacity_gate_reason": None,
                "direction": mapped_direction,
                "error_code": "candidate_requires_long_or_short",
                "raw_status": "candidate_requires_long_or_short",
                "adapter_classification": classification,
            }
        if not _has_directional_geometry(fixture):
            return {
                "state": "invalid",
                "comparability": "comparable" if comparable else "not_comparable",
                "profile_declared_state": declared_state,
                "profile_declared_direction": declared_direction,
                "capacity_gate_reason": None,
                "direction": mapped_direction,
                "error_code": "directional_without_geometry",
                "raw_status": "directional_without_geometry",
                "adapter_classification": classification,
            }

    return {
        "state": mapped_state,
        "comparability": "comparable" if comparable else "not_comparable",
        "profile_declared_state": declared_state,
        "profile_declared_direction": declared_direction,
        "capacity_gate_reason": None,
        "direction": mapped_direction,
        "error_code": None,
        "raw_status": None,
        "adapter_classification": classification,
    }
