"""Thin HTTP client for the local Glitch Topstep gateway."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8790"


def gateway_url() -> str:
    value = os.environ.get("GLITCH_TOPSTEP_GATEWAY_URL", DEFAULT_GATEWAY_URL).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise RuntimeError("GLITCH_TOPSTEP_GATEWAY_URL must be a bare HTTP(S) origin")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("GLITCH_TOPSTEP_GATEWAY_URL must use HTTP(S)")
    if parsed.scheme != "https" and not loopback:
        raise RuntimeError("non-loopback gateway URLs must use HTTPS")
    return value


def local_token() -> str:
    token = os.environ.get("GLITCH_TOPSTEP_LOCAL_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GLITCH_TOPSTEP_LOCAL_TOKEN is not configured")
    return token


def request_timeout_seconds() -> float:
    raw = os.environ.get("GLITCH_TOPSTEP_REQUEST_TIMEOUT_SECONDS", "20")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 20.0


def request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        gateway_url() + path,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout_seconds()) as response:
            payload = response.read().decode("utf-8", errors="replace")
            value = json.loads(payload or "{}")
            if not isinstance(value, dict):
                raise ValueError("gateway response must be a JSON object")
            return int(response.status), value
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(payload or "{}")
        except json.JSONDecodeError:
            value = {"error": "http_error", "message": payload}
        if not isinstance(value, dict):
            value = {"error": "http_error", "body": value}
        return int(error.code), value
