"""Gateway read-only snapshot fetch for shadow observation — GET only, zero mutations."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from common import local_token, utc_now
from ensemble_envelope import build_evaluation_envelope
from ensemble_envelope_seal import envelope_validity_seconds, sealed_envelope_identity

READONLY_SCHEMA = "glitch.topstep.shadow_gateway_readonly.v1"
DEFAULT_GATEWAY = "http://127.0.0.1:8790"


class ShadowGatewayError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def gateway_base_url() -> str:
    return os.environ.get("GLITCH_GATEWAY_URL", DEFAULT_GATEWAY).rstrip("/")


def _http_get_json(path: str, *, token: str, timeout_s: float = 5.0) -> tuple[int, dict[str, Any]]:
    url = f"{gateway_base_url()}{path}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except URLError as exc:
        raise ShadowGatewayError("gateway_unavailable", str(exc)) from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise ShadowGatewayError("gateway_timeout", str(exc)) from exc


def _maintenance_window(health: dict[str, Any]) -> bool:
    if health.get("status") == "degraded":
        return True
    recovery = health.get("recovery") if isinstance(health.get("recovery"), dict) else {}
    if recovery.get("active") is True:
        return True
    lifecycle = health.get("lifecycle") if isinstance(health.get("lifecycle"), dict) else {}
    if str(lifecycle.get("state") or "").lower() not in {"", "ready", "armed"}:
        return True
    return False


def _daily_capture_locked(packet: dict[str, Any]) -> bool:
    execution = packet.get("execution") if isinstance(packet.get("execution"), dict) else {}
    if execution.get("daily_capture_locked") is True:
        return True
    dc = packet.get("daily_capture") if isinstance(packet.get("daily_capture"), dict) else {}
    return dc.get("locked") is True


def _state_complete(health: dict[str, Any], packet: dict[str, Any]) -> bool:
    dq_h = health.get("data_quality") if isinstance(health.get("data_quality"), dict) else {}
    if dq_h.get("state_complete") is False:
        return False
    dq_p = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    return dq_p.get("state_complete") is not False


def _snapshot_expired(packet: dict[str, Any], *, max_age_ms: int) -> bool:
    dq = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    quote_age = dq.get("quote_age_ms")
    if isinstance(quote_age, (int, float)) and not isinstance(quote_age, bool):
        return int(quote_age) > max_age_ms
    return False


def fetch_gateway_health_readonly(
    *,
    token: str | None = None,
    http_get: Callable[[str, str, float], tuple[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """GET /health only — market gate without minting a new packet_id."""
    tok = token if token is not None else local_token()
    getter = http_get or (lambda path, t, timeout: _http_get_json(path, token=t, timeout_s=timeout))
    status, health = getter("/health", tok, 5.0)
    if status != 200:
        raise ShadowGatewayError("gateway_unavailable", f"health_status_{status}")
    if _maintenance_window(health):
        raise ShadowGatewayError("maintenance_window")
    return health


def fetch_gateway_readonly_snapshot(
    *,
    matrix: dict[str, Any],
    mapping: dict[str, Any],
    budget: dict[str, Any] | None = None,
    token: str | None = None,
    http_get: Callable[[str, str, float], tuple[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """GET /health and /packet only. Raises ShadowGatewayError on blockers."""
    tok = token if token is not None else local_token()
    getter = http_get or (lambda path, t, timeout: _http_get_json(path, token=t, timeout_s=timeout))

    status, health = getter("/health", tok, 5.0)
    if status != 200:
        raise ShadowGatewayError("gateway_unavailable", f"health_status_{status}")
    if _maintenance_window(health):
        raise ShadowGatewayError("maintenance_window")

    pstatus, packet = getter("/packet", tok, 5.0)
    if pstatus != 200 or not isinstance(packet, dict):
        raise ShadowGatewayError("gateway_unavailable", f"packet_status_{pstatus}")

    if not _state_complete(health, packet):
        raise ShadowGatewayError("state_incomplete")
    if _daily_capture_locked(packet):
        raise ShadowGatewayError("daily_capture_locked")

    max_age = int((budget or {}).get("max_snapshot_age_ms") or 120_000)
    if _snapshot_expired(packet, max_age_ms=max_age):
        raise ShadowGatewayError("snapshot_expired")

    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    if market.get("quote_valid") is False:
        raise ShadowGatewayError("market_not_valid")

    envelope = build_evaluation_envelope(
        packet=packet,
        source_catalog=matrix["source_catalog"],
        reference_utc=str(packet.get("created_utc") or utc_now()),
        frame_id=str(packet.get("packet_id") or "gateway-packet"),
        corpus_ref="shadow_gateway_readonly",
        mapping=mapping,
    )
    validity = envelope_validity_seconds(budget=budget)
    envelope["validity_seconds"] = validity
    identity = sealed_envelope_identity(envelope)
    envelope["envelope_hash"] = identity["envelope_hash"]
    envelope["frame_id"] = str(packet.get("packet_id") or "gateway-packet")
    envelope["packet"] = packet

    return {
        "schema_version": READONLY_SCHEMA,
        "fetched_utc": utc_now(),
        "gateway_url": gateway_base_url(),
        "health": health,
        "packet_id": packet.get("packet_id"),
        "envelope": envelope,
        "identity": identity,
        "methods_used": ["GET /health", "GET /packet"],
        "mutations": [],
    }
