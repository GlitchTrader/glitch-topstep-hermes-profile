"""Sanitize gateway packets for model prompts.

The current decision packet stays full (minus provider IDs). Historical minute
frames are compact continuity snapshots that preserve every collected semantic
field while omitting prompt-template noise and packet lease metadata.
"""
from __future__ import annotations

import copy
from typing import Any

FRAME_SNAPSHOT_SCHEMA = "glitch.topstep.frame_snapshot.v2"

# Top-level packet keys preserved in every frame snapshot.
FRAME_PACKET_KEYS = (
    "schema_version",
    "packet_id",
    "created_utc",
    "venue",
    "firm",
    "instrument",
    "account",
    "contract",
    "market",
    "market_observation",
    "order_flow",
    "data_quality",
    "execution",
    "policy",
    "position_state",
    "protection",
    "reconciliation",
    "session_activity",
    "orders_working",
)


def _strip_provider_ids(packet: dict[str, Any], *, drop_template: bool) -> dict[str, Any]:
    value = copy.deepcopy(packet)
    account = value.get("account")
    if isinstance(account, dict):
        account.pop("id", None)
    contract = value.get("contract")
    if isinstance(contract, dict):
        contract.pop("id", None)
        contract.pop("symbol_id", None)
    if drop_template:
        value.pop("required_output_template", None)
    value.pop("expires_utc", None)
    return value


def packet_for_model(
    packet: dict[str, Any],
    *,
    profile_name: str,
    core_model: str,
    prompt_version: str,
) -> dict[str, Any]:
    value = _strip_provider_ids(packet, drop_template=False)
    template = value.get("required_output_template")
    if isinstance(template, dict):
        template = copy.deepcopy(template)
        template["operator_profile"] = profile_name
        template["model_version"] = core_model
        template["prompt_version"] = prompt_version
        value["required_output_template"] = template
    return value


def frame_for_model(frame: dict[str, Any]) -> dict[str, Any]:
    packet = frame.get("packet")
    if not isinstance(packet, dict):
        return {
            "schema_version": FRAME_SNAPSHOT_SCHEMA,
            "minute_id": frame.get("minute_id"),
            "captured_utc": frame.get("captured_utc"),
            "packet": {},
        }

    slim = _strip_provider_ids(packet, drop_template=True)
    return {
        "schema_version": FRAME_SNAPSHOT_SCHEMA,
        "minute_id": frame.get("minute_id"),
        "captured_utc": frame.get("captured_utc"),
        "packet": slim,
    }


def frame_packet_keys(packet: dict[str, Any]) -> set[str]:
    return {key for key in FRAME_PACKET_KEYS if key in packet}
