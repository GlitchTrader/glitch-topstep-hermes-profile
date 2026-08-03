"""Profile ↔ gateway compatibility contract for glitch-topstep-hermes-profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from distribution_manifest import read_distribution_version, PROMPT_VERSION

_PROFILE_VERSION = read_distribution_version(Path(__file__).resolve().parent.parent)

PROFILE_COMPATIBILITY: dict[str, Any] = {
    "profile_name": "glitch-topstep",
    "profile_version": _PROFILE_VERSION,
    "setup_schema": "glitch.topstep.hermes.setup.v1",
    "operator_schema": "glitch.topstep.hermes.operator.v2",
    "intent_schema": "glitch.intent.v2",
    "decision_packet_schemas": [
        "glitch.direct.decision_packet.v1",
        "glitch.direct.decision_packet.v2",
    ],
    "prompt_version": PROMPT_VERSION,
    "health_schema": "glitch.direct.health.v2",
    "gateway_name": "glitch-topstep",
    "min_gateway_version": "0.1.1",
    "tested_gateway_version": "0.1.2",
    "hermes_requires": ">=0.18.2",
    "required_capabilities": [
        "packet_supported_actions",
        "durable_mutation_receipts",
        "restart_reconciliation",
    ],
}


def parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in str(value).strip().split("."):
        if not segment.isdigit():
            raise ValueError(f"invalid version segment: {value!r}")
        parts.append(int(segment))
    if not parts:
        raise ValueError(f"invalid version: {value!r}")
    return tuple(parts)


def version_at_least(actual: str, minimum: str) -> bool:
    return parse_version(actual) >= parse_version(minimum)


def compatibility_issues(health: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if health.get("schema_version") != PROFILE_COMPATIBILITY["health_schema"]:
        issues.append(
            "health_schema_mismatch:"
            f"{health.get('schema_version')!r}!={PROFILE_COMPATIBILITY['health_schema']!r}"
        )

    contract = health.get("compatibility")
    if not isinstance(contract, dict):
        issues.append("gateway_missing_compatibility_contract")
        return issues

    if contract.get("gateway_name") != PROFILE_COMPATIBILITY["gateway_name"]:
        issues.append(
            "gateway_name_mismatch:"
            f"{contract.get('gateway_name')!r}!={PROFILE_COMPATIBILITY['gateway_name']!r}"
        )

    gateway_version = str(contract.get("gateway_version") or "").strip()
    if not gateway_version:
        issues.append("gateway_version_missing")
    elif not version_at_least(
        gateway_version,
        str(PROFILE_COMPATIBILITY["min_gateway_version"]),
    ):
        issues.append(
            "gateway_version_too_old:"
            f"{gateway_version}<{PROFILE_COMPATIBILITY['min_gateway_version']}"
        )

    intent_schemas = contract.get("intent_schemas")
    if not isinstance(intent_schemas, list):
        issues.append("intent_schemas_missing")
    elif PROFILE_COMPATIBILITY["intent_schema"] not in intent_schemas:
        issues.append(
            "intent_schema_unsupported:"
            f"{PROFILE_COMPATIBILITY['intent_schema']!r}"
        )

    packet_schemas = contract.get("decision_packet_schemas")
    required_packets = set(PROFILE_COMPATIBILITY["decision_packet_schemas"])
    if not isinstance(packet_schemas, list):
        issues.append("decision_packet_schemas_missing")
    else:
        missing_packets = sorted(required_packets - set(packet_schemas))
        if missing_packets:
            issues.append(
                "decision_packet_schemas_missing:" + ",".join(missing_packets)
            )

    capabilities = contract.get("capabilities")
    if not isinstance(capabilities, list):
        issues.append("capabilities_missing")
    else:
        capability_set = set(capabilities)
        missing_capabilities = [
            item
            for item in PROFILE_COMPATIBILITY["required_capabilities"]
            if item not in capability_set
        ]
        if missing_capabilities:
            issues.append(
                "capabilities_missing:" + ",".join(missing_capabilities)
            )

    return issues


def verify_gateway_compatibility(health: dict[str, Any]) -> None:
    issues = compatibility_issues(health)
    if issues:
        raise RuntimeError("gateway_incompatible:" + ";".join(issues))


def compatibility_summary(health: dict[str, Any]) -> str:
    contract = health.get("compatibility")
    if not isinstance(contract, dict):
        return "incompatible (gateway_missing_compatibility_contract)"
    issues = compatibility_issues(health)
    if issues:
        return "incompatible (" + "; ".join(issues) + ")"
    gateway_version = str(contract.get("gateway_version") or "unknown")
    return (
        f"compatible (profile {PROFILE_COMPATIBILITY['profile_version']}, "
        f"gateway {gateway_version})"
    )
