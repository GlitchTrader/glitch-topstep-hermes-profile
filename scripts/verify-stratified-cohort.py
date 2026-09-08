"""Verify stratified cohort manifest (offline, no Hermes)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(
    manifest_path: Path,
    repo: Path,
    *,
    scenarios_override: Path | None = None,
) -> dict[str, Any]:
    manifest = _load(manifest_path)
    enriched_path = repo / "tests" / "fixtures" / "frozen_corpus" / "enriched" / "manifest.json"
    enriched = _load(enriched_path)
    by_frame = {str(e.get("frame_id")): e for e in enriched.get("entries") or [] if isinstance(e, dict)}
    queue = manifest.get("collection_queue") or []
    errors: list[str] = []
    seen_hashes: set[str] = set()
    seen_frames: set[str] = set()
    for row in queue:
        if not isinstance(row, dict):
            errors.append("invalid_queue_row")
            continue
        frame_id = str(row.get("frame_id") or "")
        snap = str(row.get("snapshot_hash") or "")
        if frame_id in seen_frames:
            errors.append(f"duplicate_frame_id:{frame_id}")
        if snap in seen_hashes:
            errors.append(f"duplicate_snapshot_hash:{snap}")
        seen_frames.add(frame_id)
        seen_hashes.add(snap)
        entry = by_frame.get(frame_id)
        if not entry:
            errors.append(f"missing_enriched_entry:{frame_id}")
            continue
        if not row.get("capacity_gate_validated") and str(entry.get("snapshot_hash")) != snap:
            errors.append(f"snapshot_hash_mismatch:{frame_id}")
        corpus_file = repo / "tests" / "fixtures" / "frozen_corpus" / "enriched" / str(entry.get("corpus_file"))
        if not corpus_file.is_file():
            errors.append(f"missing_corpus_file:{frame_id}")
    excluded = set(manifest.get("excluded_frame_ids") or [])
    overlap = excluded & seen_frames
    if overlap:
        errors.append(f"excluded_frame_reused:{sorted(overlap)}")

    corpus_report: dict[str, Any] | None = None
    if scenarios_override is not None:
        scenarios_path = scenarios_override
    elif manifest.get("scenarios_path"):
        scenarios_path = repo / str(manifest["scenarios_path"])
    else:
        scenarios_path = manifest_path.parent.parent / "stratified_scenarios.v1.json"
    if scenarios_path.is_file():
        import importlib.util
        import sys

        scripts = repo / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from validate_comparable_corpus import validate_comparable_corpus

        corpus_report = validate_comparable_corpus(repo_root=repo, scenarios_path=scenarios_path)
        if not corpus_report.get("all_valid"):
            errors.append(
                f"corpus_validation_failed:{corpus_report.get('valid_count')}/{corpus_report.get('scenario_count')}"
            )
        validated_by_frame = {
            str(row.get("frame_id")): row for row in corpus_report.get("scenarios") or [] if isinstance(row, dict)
        }
        for row in queue:
            if not isinstance(row, dict):
                continue
            frame_id = str(row.get("frame_id") or "")
            validated = validated_by_frame.get(frame_id)
            if not validated:
                continue
            expected = str(validated.get("computed_snapshot_hash") or "")
            if expected and str(row.get("snapshot_hash") or "") != expected:
                errors.append(f"computed_snapshot_hash_mismatch:{frame_id}")

    return {
        "ok": not errors,
        "manifest_path": str(manifest_path),
        "envelope_count": len(queue),
        "unique_snapshot_hashes": len(seen_hashes),
        "corpus_validation": corpus_report,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify stratified cohort manifest")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO / "evaluation" / "runs" / "stratified-cohort-manifest-v3-2026-09-01.json",
    )
    parser.add_argument("--scenarios", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else args.repo_root / args.manifest
    scenarios = args.scenarios
    if scenarios is not None and not scenarios.is_absolute():
        scenarios = args.repo_root / scenarios
    report = verify_manifest(manifest_path, args.repo_root, scenarios_override=scenarios)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
