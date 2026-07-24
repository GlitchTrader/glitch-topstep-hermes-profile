from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROFILE_NAME = "glitch-topstep"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8790"


def windows_hidden_subprocess_flags() -> int:
    if sys.platform != "win32":
        return 0
    return (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def profile_root(profile: str = PROFILE_NAME) -> Path:
    explicit = os.environ.get("HERMES_HOME")
    if explicit:
        resolved = Path(explicit).expanduser().resolve()
        if resolved.name == profile:
            return resolved
        nested = resolved / "profiles" / profile
        if nested.is_dir():
            return nested.resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "hermes" / "profiles" / profile).resolve()
    return (Path.home() / ".hermes" / "profiles" / profile).resolve()


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def configure_environment(root: Path | None = None) -> Path:
    resolved = (root or profile_root()).resolve()
    load_dotenv(resolved / ".env")
    return resolved


def gateway_url() -> str:
    return os.environ.get("GLITCH_TOPSTEP_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return read_json(path) if path.is_file() else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, separators=(",", ":"), ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")


def tail_jsonl(path: Path, count: int) -> list[dict[str, Any]]:
    return read_jsonl(path)[-max(0, count):]


def prune_files(paths: Iterable[Path], keep: int) -> None:
    ordered = sorted(paths, key=lambda item: item.name, reverse=True)
    for path in ordered[max(0, keep):]:
        try:
            path.unlink()
        except OSError:
            pass


def extract_single_json_object(text: str, *, schema: str | None = None) -> dict[str, Any]:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError("model output must be a JSON object")
        return value
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        candidates: list[dict[str, Any]] = []
        for index, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(stripped, index)
            except json.JSONDecodeError:
                continue
            if not isinstance(candidate, dict):
                continue
            if schema is None or candidate.get("schema_version") == schema:
                candidates.append(candidate)
        unique = []
        seen = set()
        for candidate in candidates:
            encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
            if encoded not in seen:
                seen.add(encoded)
                unique.append(candidate)
        if len(unique) != 1:
            raise original_error
        return unique[0]
