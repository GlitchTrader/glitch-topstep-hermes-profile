"""Age-based retention for profile state artifacts (NT packet-prune analogue)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import collect_referenced_packet_ids


DEFAULT_RETENTION_HOURS = 72
PRUNE_STATE_FILENAME = "prune-state.json"


def retention_hours() -> int:
    try:
        return max(1, int(os.environ.get("GLITCH_TOPSTEP_STATE_RETENTION_HOURS", str(DEFAULT_RETENTION_HOURS))))
    except ValueError:
        return DEFAULT_RETENTION_HOURS


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _file_mtime_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _prune_state_path(state: Path) -> Path:
    return state / PRUNE_STATE_FILENAME


def _should_run_prune(state: Path, now: datetime) -> bool:
    path = _prune_state_path(state)
    if not path.is_file():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        last = _parse_utc(payload.get("last_prune_utc"))
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return True
    if last is None:
        return True
    return (now - last).total_seconds() >= 3600


def prune_old_json_files(
    directory: Path,
    cutoff: datetime,
    *,
    status_allow: set[str] | None = None,
    preserve_stems: set[str] | None = None,
) -> int:
    if not directory.is_dir():
        return 0
    preserve = preserve_stems or set()
    removed = 0
    for path in directory.glob("*.json"):
        if path.stem in preserve:
            continue
        try:
            if status_allow is not None:
                doc = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(doc, dict) or str(doc.get("status") or "") not in status_allow:
                    continue
                stamp = _parse_utc(doc.get("completed_utc") or doc.get("recorded_utc") or doc.get("started_utc"))
            else:
                stamp = None
            if stamp is None:
                stamp = _file_mtime_utc(path)
            if stamp <= cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            continue
    return removed


def prune_jsonl_by_age(path: Path, cutoff: datetime, *, stamp_keys: tuple[str, ...]) -> int:
    """Rewrite jsonl keeping rows at or after cutoff. Returns dropped count."""
    if not path.is_file():
        return 0
    kept: list[str] = []
    dropped = 0
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if not isinstance(row, dict):
            kept.append(line)
            continue
        stamp = None
        for key in stamp_keys:
            stamp = _parse_utc(row.get(key))
            if stamp is not None:
                break
        if stamp is not None and stamp < cutoff:
            dropped += 1
            continue
        kept.append(line)
    if dropped:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                if kept:
                    stream.write("\n".join(kept) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return dropped


def prune_state_retention(state: Path, *, now: datetime | None = None) -> dict[str, int]:
    """Bound local state growth; preserve referenced packets (audit W5/W6)."""
    recorded = now or datetime.now(timezone.utc)
    if not _should_run_prune(state, recorded):
        return {"skipped_cadence": 1}
    cutoff = recorded - timedelta(hours=retention_hours())
    referenced = collect_referenced_packet_ids(state)
    result = {
        "receipts_removed": prune_old_json_files(state / "receipts", cutoff),
        "attempts_removed": prune_old_json_files(
            state / "attempts",
            cutoff,
            status_allow={
                "completed",
                "failed",
                "stale_packet_discarded",
                "execution_failed",
                "decision_ready",
            },
        ),
        "minute_frames_removed": prune_old_json_files(
            state / "minute-frames",
            cutoff,
            preserve_stems=referenced,
        ),
        "minute_frames_preserved": len(referenced),
        "execution_facts_dropped": prune_jsonl_by_age(
            state / "execution-facts.jsonl",
            cutoff,
            stamp_keys=("recorded_utc", "occurred_utc", "created_utc"),
        ),
        "events_dropped": prune_jsonl_by_age(
            state / "events.jsonl",
            cutoff,
            stamp_keys=("recorded_utc",),
        ),
    }
    _prune_state_path(state).write_text(
        json.dumps(
            {
                "schema_version": "glitch.topstep.prune_state.v1",
                "last_prune_utc": recorded.isoformat().replace("+00:00", "Z"),
                "referenced_packet_count": len(referenced),
                "result": result,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return result
