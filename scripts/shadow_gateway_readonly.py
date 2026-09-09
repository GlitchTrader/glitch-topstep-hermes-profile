"""Gateway read-only snapshot fetch for shadow observation — GET only, zero mutations."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from common import local_token, utc_now
from ensemble_envelope import build_evaluation_envelope
from ensemble_envelope_seal import envelope_validity_seconds, sealed_envelope_identity

READONLY_SCHEMA = "glitch.topstep.shadow_gateway_readonly.v1"
DEFAULT_GATEWAY = "http://127.0.0.1:8790"
DEFAULT_HEALTH_TIMEOUT_S = 5.0
DEFAULT_PACKET_TIMEOUT_S = 8.0
DEFAULT_PACKET_MAX_ATTEMPTS = 3
DEFAULT_PACKET_RETRY_DELAY_S = 0.25


@dataclass
class GatewayHttpAttempt:
    endpoint: str
    attempt: int
    duration_ms: int
    error: str | None = None


@dataclass
class GatewayHttpResult:
    status: int
    body: dict[str, Any]
    attempts: list[GatewayHttpAttempt] = field(default_factory=list)


class ShadowGatewayError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def gateway_base_url() -> str:
    return os.environ.get("GLITCH_GATEWAY_URL", DEFAULT_GATEWAY).rstrip("/")


def _http_get_json_once(path: str, *, token: str, timeout_s: float) -> tuple[int, dict[str, Any]]:
    url = f"{gateway_base_url()}{path}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    with urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body) if body else {}


def _http_get_json_bounded(
    path: str,
    *,
    token: str,
    timeout_s: float,
    max_attempts: int = 1,
    retry_delay_s: float = 0.0,
) -> GatewayHttpResult:
    attempts: list[GatewayHttpAttempt] = []
    last_code = "gateway_timeout"
    last_detail = ""
    for attempt in range(1, max(1, max_attempts) + 1):
        started = time.monotonic()
        try:
            status, body = _http_get_json_once(path, token=token, timeout_s=timeout_s)
            duration_ms = int((time.monotonic() - started) * 1000)
            attempts.append(
                GatewayHttpAttempt(endpoint=path, attempt=attempt, duration_ms=duration_ms),
            )
            return GatewayHttpResult(status=status, body=body, attempts=attempts)
        except URLError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            last_code = "gateway_unavailable"
            last_detail = str(exc)
            attempts.append(
                GatewayHttpAttempt(
                    endpoint=path,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error=last_code,
                ),
            )
        except (TimeoutError, json.JSONDecodeError) as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            last_code = "gateway_timeout"
            last_detail = str(exc)
            attempts.append(
                GatewayHttpAttempt(
                    endpoint=path,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error=last_code,
                ),
            )
        if attempt < max_attempts:
            time.sleep(retry_delay_s)
    raise ShadowGatewayError(
        last_code,
        json.dumps({"attempts": [a.__dict__ for a in attempts], "detail": last_detail}),
    )


def _http_get_json(path: str, *, token: str, timeout_s: float = 5.0) -> tuple[int, dict[str, Any]]:
    try:
        result = _http_get_json_bounded(path, token=token, timeout_s=timeout_s, max_attempts=1)
        return result.status, result.body
    except ShadowGatewayError as exc:
        raise exc


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
    dq_p = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    # Fail closed: missing state_complete is not treated as complete.
    return dq_h.get("state_complete") is True and dq_p.get("state_complete") is True


def _snapshot_expired(packet: dict[str, Any], *, max_age_ms: int) -> bool:
    dq = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    quote_age = dq.get("quote_age_ms")
    if isinstance(quote_age, (int, float)) and not isinstance(quote_age, bool):
        return int(quote_age) > max_age_ms
    return False


def _deferred_data_quality_detail(health: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any] | None:
    health_dq = health.get("data_quality") if isinstance(health.get("data_quality"), dict) else {}
    packet_dq = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    health_issues = set(health_dq.get("issues") or [])
    packet_issues = set(packet_dq.get("issues") or [])
    if "quote_geometry_invalid" not in health_issues and "quote_geometry_invalid" not in packet_issues:
        return None
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    return {
        "reason": "quote_geometry_invalid",
        "health_state_complete": health_dq.get("state_complete"),
        "packet_state_complete": packet_dq.get("state_complete"),
        "health_issues": sorted(health_issues),
        "packet_issues": sorted(packet_issues),
        "quote_timestamp": market.get("quote_timestamp"),
        "quote_valid": market.get("quote_valid"),
        "last_invalid": health_dq.get("quote_geometry_last_invalid"),
    }


def fetch_gateway_health_raw(
    *,
    token: str | None = None,
    http_get: Callable[[str, str, float], tuple[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """GET /health without maintenance classification — for stability window sampling."""
    tok = token if token is not None else local_token()
    getter = http_get or (lambda path, t, timeout: _http_get_json(path, token=t, timeout_s=timeout))
    status, health = getter("/health", tok, 5.0)
    if status != 200:
        raise ShadowGatewayError("gateway_unavailable", f"health_status_{status}")
    return health


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


def fetch_gateway_packet_readonly(
    *,
    token: str | None = None,
    http_get: Callable[[str, str, float], tuple[int, dict[str, Any]]] | None = None,
    timeout_s: float = DEFAULT_PACKET_TIMEOUT_S,
    max_attempts: int = DEFAULT_PACKET_MAX_ATTEMPTS,
    retry_delay_s: float = DEFAULT_PACKET_RETRY_DELAY_S,
) -> dict[str, Any]:
    tok = token if token is not None else local_token()
    if http_get is not None:
        status, packet = http_get("/packet", tok, timeout_s)
        if status != 200 or not isinstance(packet, dict):
            raise ShadowGatewayError("gateway_unavailable", f"packet_status_{status}")
        return packet
    result = _http_get_json_bounded(
        "/packet",
        token=tok,
        timeout_s=timeout_s,
        max_attempts=max_attempts,
        retry_delay_s=retry_delay_s,
    )
    if result.status != 200 or not isinstance(result.body, dict):
        raise ShadowGatewayError(
            "gateway_unavailable",
            json.dumps({"status": result.status, "attempts": [a.__dict__ for a in result.attempts]}),
        )
    return result.body


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

    deferred = _deferred_data_quality_detail(health, packet)
    if deferred is not None:
        raise ShadowGatewayError("deferred_data_quality", json.dumps(deferred, sort_keys=True))

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
