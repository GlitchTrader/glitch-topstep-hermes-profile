"""Compute immutable digest for a stratified cohort manifest (offline)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def cohort_digest(manifest: dict[str, Any]) -> dict[str, Any]:
    queue = manifest.get("collection_queue") or []
    rows: list[dict[str, Any]] = []
    for row in sorted(queue, key=lambda r: int(r.get("queue_order") or 0)):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "queue_order": row.get("queue_order"),
                "scenario_id": row.get("scenario_id"),
                "frame_id": row.get("frame_id"),
                "snapshot_hash": row.get("snapshot_hash"),
                "envelope_id": row.get("envelope_id"),
                "envelope_hash": row.get("envelope_hash"),
                "scenario_tag": row.get("scenario_tag"),
                "origin": row.get("origin"),
                "capacity_gate_validated": row.get("capacity_gate_validated"),
            }
        )
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "schema_version": "glitch.topstep.stratified_cohort_digest.v1",
        "manifest_schema": manifest.get("schema_version"),
        "cohort_version": manifest.get("cohort_version") or manifest.get("status"),
        "envelope_count": len(rows),
        "sha256": digest,
        "envelopes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest stratified cohort manifest")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO / "evaluation" / "runs" / "stratified-cohort-manifest-v3-2026-09-01.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "evaluation" / "runs" / "stratified-cohort-digest-v3-2026-09-01.json",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = cohort_digest(manifest)
    out = args.output if args.output.is_absolute() else REPO / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "sha256": report["sha256"], "envelopes": report["envelope_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
