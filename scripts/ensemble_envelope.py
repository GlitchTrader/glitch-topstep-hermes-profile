"""Build and hash glitch.topstep.evaluation_envelope.v1 from frozen packets."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


COMPLETENESS_STATES = frozenset({
    "available",
    "stale",
    "partial",
    "inconsistent",
    "not_applicable",
    "missing_required",
})

ENVELOPE_SCHEMA = "glitch.topstep.evaluation_envelope.v1"
MAPPING_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "packet_envelope_mapping.v1.json"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_packet_envelope_mapping(path: Path | None = None) -> dict[str, Any]:
    mapping_path = path or MAPPING_PATH
    value = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("packet_envelope_mapping_invalid")
    return value


def normalize_contract(contract: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    fields = mapping.get("normalized_contract_fields", [])
    if not isinstance(fields, list):
        return dict(contract)
    return {key: contract[key] for key in fields if key in contract}


def packet_canonical_subset(packet: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    copied = mapping.get("copied_packet_fields", [])
    if not isinstance(copied, list):
        raise ValueError("mapping_copied_packet_fields_missing")
    subset: dict[str, Any] = {}
    for field in copied:
        if field not in packet:
            continue
        value = packet[field]
        if field == "contract" and isinstance(value, dict):
            subset[field] = normalize_contract(value, mapping)
        elif field == "instrument" and isinstance(value, str):
            subset[field] = value.strip().upper()
        else:
            subset[field] = value
    for prohibited in mapping.get("prohibited_packet_fields", []):
        subset.pop(str(prohibited), None)
    return subset


def assert_accepted_packet_schema(packet: dict[str, Any], mapping: dict[str, Any]) -> str:
    accepted = mapping.get("accepted_packet_schema_versions", [])
    if not isinstance(accepted, list) or not accepted:
        raise ValueError("mapping_accepted_packet_schema_versions_missing")
    version = str(packet.get("schema_version") or "")
    if version in accepted:
        return version
    policy = str(mapping.get("unknown_packet_schema_policy") or "reject_envelope_build")
    if policy == "reject_envelope_build":
        raise ValueError("packet_schema_version_not_accepted")
    return str(accepted[0])


def snapshot_hash(packet_subset: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(packet_subset)).hexdigest()


def _has_path(packet: dict[str, Any], dotted: str) -> bool:
    current: Any = packet
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if current is None:
        return False
    if isinstance(current, (list, dict)) and len(current) == 0:
        return False
    return True


def assess_source_completeness(packet: dict[str, Any], source_id: str, paths: list[str]) -> str:
    if not paths:
        return "not_applicable"
    present = sum(1 for path in paths if _has_path(packet, path))
    if present == 0:
        return "missing_required"
    if present < len(paths):
        return "partial"
    data_quality = packet.get("data_quality")
    if isinstance(data_quality, dict) and data_quality.get("state_complete") is False:
        return "inconsistent"
    return "available"


def build_completeness(packet: dict[str, Any], source_catalog: dict[str, Any]) -> dict[str, str]:
    completeness: dict[str, str] = {}
    for source_id, meta in source_catalog.items():
        paths = meta.get("packet_paths") if isinstance(meta, dict) else None
        if not isinstance(paths, list):
            continue
        completeness[source_id] = assess_source_completeness(packet, source_id, paths)
    return completeness


def build_evaluation_envelope(
    *,
    packet: dict[str, Any],
    source_catalog: dict[str, Any],
    reference_utc: str,
    validity_seconds: int = 300,
    frame_id: str | None = None,
    corpus_ref: str | None = None,
    mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("packet_must_be_object")
    mapping_doc = mapping or load_packet_envelope_mapping()
    packet_schema_version = assert_accepted_packet_schema(packet, mapping_doc)
    packet_subset = packet_canonical_subset(packet, mapping_doc)
    snapshot_id = str(packet_subset.get("packet_id") or frame_id or uuid.uuid4())
    reference = datetime.fromisoformat(reference_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    valid_until = reference + timedelta(seconds=validity_seconds)
    instrument = str(packet_subset.get("instrument") or packet.get("instrument") or "").strip().upper()
    if not instrument:
        raise ValueError("instrument_required")
    contract_raw = packet_subset.get("contract")
    contract = contract_raw if isinstance(contract_raw, dict) else {}
    snap_hash = snapshot_hash(packet_subset)
    envelope_id = f"env-{snap_hash[:16]}"
    return {
        "schema_version": ENVELOPE_SCHEMA,
        "envelope_id": envelope_id,
        "snapshot_id": snapshot_id,
        "snapshot_hash": snap_hash,
        "reference_utc": reference.isoformat().replace("+00:00", "Z"),
        "valid_until_utc": valid_until.isoformat().replace("+00:00", "Z"),
        "instrument": instrument,
        "contract": normalize_contract(contract, mapping_doc),
        "packet_schema_version": packet_schema_version,
        "packet": packet_subset,
        "completeness": build_completeness(packet_subset, source_catalog),
        "source_refs": {
            "frame_id": frame_id or snapshot_id,
            "corpus_ref": corpus_ref or "",
            "mapping_version": str(mapping_doc.get("mapping_version") or ""),
        },
    }


def envelope_hash(envelope: dict[str, Any]) -> str:
    payload = {
        "snapshot_hash": envelope.get("snapshot_hash"),
        "reference_utc": envelope.get("reference_utc"),
        "valid_until_utc": envelope.get("valid_until_utc"),
        "instrument": envelope.get("instrument"),
        "contract": envelope.get("contract"),
        "packet_schema_version": envelope.get("packet_schema_version"),
        "completeness": envelope.get("completeness"),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
