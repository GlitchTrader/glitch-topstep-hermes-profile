"""Sanitize gateway packets for model prompts.

The current decision packet stays evidence-rich but compacts nested market
observation and order-flow blobs. Historical minute frames are continuity
snapshots with the same semantic top-level fields, without prompt-template
noise, lease metadata, or non-essential ledger tails.
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
    "session",
    "daily_economics",
    "position_state",
    "protection",
    "reconciliation",
    "session_activity",
    "orders_working",
)

FRAME_ACCOUNT_KEYS = (
    "name",
    "balance",
    "unrealized_pnl",
    "conservative_equity",
    "total_open_contracts",
    "instrument_open_contracts",
    "can_trade",
    "working_orders",
)

FRAME_MARKET_KEYS = (
    "snapshot_hash",
    "quote_timestamp",
    "last",
    "bid",
    "ask",
    "spread_ticks",
    "session_high",
    "session_low",
)

FRAME_EXECUTION_KEYS = (
    "gateway_mode",
    "supported_actions",
    "maximum_additional_contracts",
    "new_exposure_technically_supported",
)

FRAME_POLICY_KEYS = (
    "max_contracts",
    "current_buffer_usd",
    "hard_loss_floor_usd",
    "loss_model",
)

FRAME_SESSION_KEYS = ("entry_window_open", "must_flat_utc")

FRAME_SKIP_WHEN_FLAT = frozenset(
    {"protection", "reconciliation", "session_activity", "orders_working"}
)

CYCLE_ORDER_FLOW_WINDOWS = frozenset({15, 60, 300})


def _order_flow_window_seconds(window: dict[str, Any]) -> int | None:
    seconds = window.get("window_seconds")
    if isinstance(seconds, str):
        value = seconds.removesuffix("s")
        if value.isdigit():
            return int(value)
        return None
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        return int(seconds)
    return None


def _pick(mapping: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: mapping[key] for key in keys if key in mapping}


def _packet_positioned(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    if isinstance(account, dict):
        for field in ("instrument_open_contracts", "total_open_contracts"):
            value = account.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if int(value) > 0:
                    return True
    position = packet.get("position_state")
    if isinstance(position, dict):
        side = str(position.get("side") or "").upper()
        if side and side != "FLAT":
            return True
    return False


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


def compact_timeframe_observation(timeframe: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "timeframe_minutes": timeframe.get("timeframe_minutes"),
        "latest_bar_utc": timeframe.get("latest_bar_utc"),
        "latest_bar_partial": timeframe.get("latest_bar_partial"),
    }
    features = timeframe.get("features")
    if isinstance(features, dict):
        compact["features"] = features
    close = timeframe.get("close")
    if close is not None and "features" not in compact:
        compact["close"] = close
    return compact


def compact_market_observation_state(state: Any) -> Any:
    if not isinstance(state, dict):
        return state
    observation = state.get("observation")
    if not isinstance(observation, dict):
        return {
            "last_succeeded_utc": state.get("last_succeeded_utc"),
            "last_error": state.get("last_error"),
        }
    timeframes = observation.get("timeframes")
    compact_timeframes: list[dict[str, Any]] = []
    if isinstance(timeframes, list):
        for row in timeframes:
            if isinstance(row, dict):
                compact_timeframes.append(compact_timeframe_observation(row))
    elif isinstance(timeframes, dict):
        for key, row in timeframes.items():
            if isinstance(row, dict):
                item = compact_timeframe_observation(row)
                item.setdefault("timeframe_minutes", key)
                compact_timeframes.append(item)
    return {
        "last_succeeded_utc": state.get("last_succeeded_utc"),
        "last_error": state.get("last_error"),
        "observation": {
            "schema_version": observation.get("schema_version"),
            "instrument": observation.get("instrument"),
            "timeframes": compact_timeframes,
        },
    }


def compact_order_flow_state(state: Any) -> Any:
    if not isinstance(state, dict):
        return state
    observation = state.get("observation")
    if not isinstance(observation, dict):
        return {
            "last_succeeded_utc": state.get("last_succeeded_utc"),
            "last_error": state.get("last_error"),
        }
    windows = observation.get("windows")
    compact_windows: list[dict[str, Any]] = []
    if isinstance(windows, list):
        for window in windows:
            if not isinstance(window, dict):
                continue
            seconds = _order_flow_window_seconds(window)
            if seconds in CYCLE_ORDER_FLOW_WINDOWS:
                compact_windows.append(window)
        compact_windows.sort(
            key=lambda row: _order_flow_window_seconds(row) or 0,
        )
    elif isinstance(windows, dict):
        for key in ("15s", "15", "60s", "60", "300s", "300"):
            window = windows.get(key)
            if isinstance(window, dict):
                compact_windows.append(window)
    depth = observation.get("depth")
    compact_depth = None
    if isinstance(depth, dict):
        compact_depth = _pick(
            depth,
            (
                "best_bid",
                "best_ask",
                "spread_ticks",
                "imbalance_ratio",
                "bid_volume",
                "ask_volume",
            ),
        )
    return {
        "last_succeeded_utc": state.get("last_succeeded_utc"),
        "last_error": state.get("last_error"),
        "observation": {
            "schema_version": observation.get("schema_version"),
            "windows": compact_windows,
            "depth": compact_depth,
            "issues": observation.get("issues") or [],
        },
    }


def compact_packet_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(packet)
    if "market_observation" in value:
        value["market_observation"] = compact_market_observation_state(
            value.get("market_observation")
        )
    if "order_flow" in value:
        value["order_flow"] = compact_order_flow_state(value.get("order_flow"))
    return value


def continuity_packet_for_cycle(
    packet: dict[str, Any],
    *,
    positioned: bool | None = None,
) -> dict[str, Any]:
    slim = _strip_provider_ids(packet, drop_template=True)
    if positioned is None:
        positioned = _packet_positioned(slim)
    out: dict[str, Any] = {}
    for key in FRAME_PACKET_KEYS:
        if key not in slim:
            continue
        if not positioned and key in FRAME_SKIP_WHEN_FLAT:
            continue
        value = slim[key]
        if key == "account" and isinstance(value, dict):
            out[key] = _pick(value, FRAME_ACCOUNT_KEYS)
        elif key == "market" and isinstance(value, dict):
            out[key] = _pick(value, FRAME_MARKET_KEYS)
        elif key == "execution" and isinstance(value, dict):
            out[key] = _pick(value, FRAME_EXECUTION_KEYS)
        elif key == "policy" and isinstance(value, dict):
            out[key] = _pick(value, FRAME_POLICY_KEYS)
        elif key == "session" and isinstance(value, dict):
            out[key] = _pick(value, FRAME_SESSION_KEYS)
        elif key == "market_observation":
            out[key] = compact_market_observation_state(value)
        elif key == "order_flow":
            out[key] = compact_order_flow_state(value)
        else:
            out[key] = value
    return out


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


def packet_for_cycle(
    packet: dict[str, Any],
    *,
    profile_name: str,
    core_model: str,
    prompt_version: str,
) -> dict[str, Any]:
    value = _strip_provider_ids(packet, drop_template=True)
    value = compact_packet_evidence(value)
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

    return {
        "schema_version": FRAME_SNAPSHOT_SCHEMA,
        "minute_id": frame.get("minute_id"),
        "captured_utc": frame.get("captured_utc"),
        "packet": continuity_packet_for_cycle(packet),
    }


def frame_packet_keys(packet: dict[str, Any]) -> set[str]:
    return {key for key in FRAME_PACKET_KEYS if key in packet}
