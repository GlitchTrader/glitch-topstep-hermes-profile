"""Canonical sealed evaluation envelope identity for ensemble runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import read_json
from ensemble_envelope import build_evaluation_envelope, envelope_hash
from ensemble_validate import validate_evaluation_envelope


def envelope_validity_seconds(
    *,
    budget: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> int:
    """Single source for envelope TTL — must match preflight, replay, and aggregator."""
    if config:
        env = config.get("envelope") or {}
        if env.get("validity_seconds") is not None:
            return int(env["validity_seconds"])
        budget = config.get("budget") or budget
    budget = budget or {}
    return int(budget.get("per_profile_timeout_ms", 35000) // 1000)


def seal_evaluation_envelope_from_frame(
    *,
    frame: dict[str, Any],
    source_catalog: dict[str, Any],
    mapping: dict[str, Any],
    validity_seconds: int,
    frame_path: str | None = None,
) -> dict[str, Any]:
    built = build_evaluation_envelope(
        packet=frame["packet"],
        source_catalog=source_catalog,
        reference_utc=str(frame.get("captured_utc") or ""),
        validity_seconds=validity_seconds,
        frame_id=str(frame.get("minute_id") or ""),
        corpus_ref=str(frame_path or ""),
        mapping=mapping,
    )
    validate_evaluation_envelope(built)
    return built


def sealed_envelope_identity(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "envelope_id": str(envelope.get("envelope_id") or ""),
        "snapshot_hash": str(envelope.get("snapshot_hash") or ""),
        "envelope_hash": envelope_hash(envelope),
        "instrument": str(envelope.get("instrument") or ""),
        "valid_until_utc": str(envelope.get("valid_until_utc") or ""),
        "validity_seconds": envelope_validity_seconds_from_envelope(envelope),
    }


def envelope_validity_seconds_from_envelope(envelope: dict[str, Any]) -> int:
    from datetime import datetime, timezone

    ref = str(envelope.get("reference_utc") or "")
    until = str(envelope.get("valid_until_utc") or "")
    if not ref or not until:
        return 0
    ref_dt = datetime.fromisoformat(ref.replace("Z", "+00:00")).astimezone(timezone.utc)
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00")).astimezone(timezone.utc)
    return max(0, int((until_dt - ref_dt).total_seconds()))


def seal_envelope_from_pin(
    *,
    envelope_pin: dict[str, Any],
    config: dict[str, Any],
    matrix: dict[str, Any],
    mapping: dict[str, Any],
    repo: Path,
) -> dict[str, Any]:
    frame_path = repo / str(envelope_pin.get("frame_path") or "")
    if not frame_path.is_file():
        raise FileNotFoundError(f"frame_missing:{frame_path}")
    frame = read_json(frame_path)
    validity = int(
        envelope_pin.get("validity_seconds")
        or envelope_validity_seconds(config=config)
    )
    return seal_evaluation_envelope_from_frame(
        frame=frame,
        source_catalog=matrix["source_catalog"],
        mapping=mapping,
        validity_seconds=validity,
        frame_path=str(frame_path.parent),
    )


def seal_envelope_from_run_config(
    *,
    config: dict[str, Any],
    matrix: dict[str, Any],
    mapping: dict[str, Any],
    repo: Path,
) -> dict[str, Any]:
    env_cfg = config.get("envelope") or {}
    frame_path = repo / str(env_cfg.get("frame_path") or "")
    if not frame_path.is_file():
        raise FileNotFoundError(f"frame_missing:{frame_path}")
    frame = read_json(frame_path)
    validity = envelope_validity_seconds(config=config)
    return seal_evaluation_envelope_from_frame(
        frame=frame,
        source_catalog=matrix["source_catalog"],
        mapping=mapping,
        validity_seconds=validity,
        frame_path=str(frame_path.parent),
    )


def assert_sealed_envelope_matches_pin(
    sealed: dict[str, Any],
    pin: dict[str, Any],
) -> list[str]:
    identity = sealed_envelope_identity(sealed)
    issues: list[str] = []
    for key in ("snapshot_hash", "envelope_hash", "envelope_id"):
        if str(identity.get(key) or "") != str(pin.get(key) or ""):
            issues.append(f"{key}_mismatch")
    return issues
