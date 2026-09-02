"""Shadow observation mode constants and package audit fields."""

from __future__ import annotations

from typing import Any

MODE_FIXTURE_OFFLINE = "fixture_offline"
MODE_SNAPSHOT_FILE = "snapshot_file"
MODE_GATEWAY_READ_ONLY_LIVE = "gateway_read_only_live"

SHADOW_MODES = frozenset({MODE_FIXTURE_OFFLINE, MODE_SNAPSHOT_FILE, MODE_GATEWAY_READ_ONLY_LIVE})
DEFAULT_SHADOW_MODE = MODE_FIXTURE_OFFLINE


def mode_flags(mode: str) -> dict[str, bool]:
    if mode == MODE_FIXTURE_OFFLINE:
        return {
            "evaluation_offline": True,
            "shadow_live": False,
            "shadow_live_read_only": False,
            "gateway_read_only": False,
        }
    if mode == MODE_SNAPSHOT_FILE:
        return {
            "evaluation_offline": True,
            "shadow_live": False,
            "shadow_live_read_only": False,
            "gateway_read_only": False,
        }
    if mode == MODE_GATEWAY_READ_ONLY_LIVE:
        return {
            "evaluation_offline": False,
            "shadow_live": False,
            "shadow_live_read_only": True,
            "gateway_read_only": True,
        }
    raise ValueError(f"unknown_shadow_mode:{mode}")


def enrich_observation_package(
    observation: dict[str, Any],
    *,
    mode: str,
    snapshot_source: str,
    profile_ids: list[str],
    aggregator_rules_version: str | None,
    registry_version: str | None = None,
) -> dict[str, Any]:
    flags = mode_flags(mode)
    invocation_ids = [
        str(row.get("invocation_id"))
        for row in observation.get("profile_decisions") or []
        if row.get("invocation_id")
    ]
    out = dict(observation)
    out.update(flags)
    out["mode"] = mode
    out["snapshot_source"] = snapshot_source
    out["profile_ids"] = profile_ids
    out["invocation_ids"] = invocation_ids
    out["aggregator_rules_version"] = aggregator_rules_version
    if registry_version:
        out["registry_version"] = registry_version
    out["package_audit"] = {
        "mode": mode,
        "snapshot_source": snapshot_source,
        "snapshot_hash": (observation.get("envelope") or {}).get("snapshot_hash"),
        "envelope_hash": (observation.get("envelope") or {}).get("envelope_hash"),
        "profile_ids": profile_ids,
        "invocation_ids": invocation_ids,
        "aggregator_rules_version": aggregator_rules_version,
        "intents_sent": observation.get("intents_sent", 0),
        "orders_sent": observation.get("orders_sent", 0),
        "writes_operacionais": observation.get("writes_operacionais", 0),
        "cost_usd": observation.get("cost_usd"),
        "latency_ms_total": observation.get("latency_ms_total"),
        **flags,
    }
    return out
