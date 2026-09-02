"""Verify frozen cohort manifest hashes and version pins (offline, no Hermes)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from common import read_json
from distribution_manifest import file_sha256

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
DEFAULT_MANIFEST = REPO / "evaluation" / "runs" / "frozen-cohort-manifest-2026-09-01.json"
MANIFEST_SCHEMA = "glitch.topstep.frozen_cohort_manifest.v1"


def sha256_file(path: Path) -> str:
    # ponytail: LF-normalize like SHA256SUMS so Linux/Windows CI agree on git-tracked files
    return file_sha256(path).lower()


def verify_frozen_cohort(
    *,
    manifest_path: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    repo = (repo_root or REPO).resolve()
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"unexpected manifest schema: {manifest.get('schema_version')}")

    drifts: list[dict[str, str]] = []
    checked: list[dict[str, str]] = []
    for rel_path, expected_hash in (manifest.get("frozen_file_hashes") or {}).items():
        file_path = repo / rel_path
        if not file_path.is_file():
            drifts.append(
                {
                    "path": rel_path,
                    "reason": "missing_file",
                    "expected_sha256": expected_hash,
                    "actual_sha256": "",
                }
            )
            continue
        actual_hash = sha256_file(file_path)
        checked.append({"path": rel_path, "sha256": actual_hash})
        if actual_hash != expected_hash:
            drifts.append(
                {
                    "path": rel_path,
                    "reason": "hash_mismatch",
                    "expected_sha256": expected_hash,
                    "actual_sha256": actual_hash,
                }
            )

    versions = manifest.get("versions") or {}
    contract_path = repo / "evaluation" / "evaluation_output_contract.v1.json"
    registry_path = repo / "evaluation" / "registry.json"
    version_drifts: list[dict[str, str]] = []
    if contract_path.is_file():
        contract = read_json(contract_path)
        adapter_version = str(contract.get("contract_version") or "")
        schema_version = str(contract.get("schema_version") or "")
        if adapter_version and adapter_version != versions.get("adapter_version"):
            version_drifts.append(
                {
                    "field": "adapter_version",
                    "expected": str(versions.get("adapter_version") or ""),
                    "actual": adapter_version,
                }
            )
        if schema_version and schema_version != versions.get("schema_version"):
            version_drifts.append(
                {
                    "field": "schema_version",
                    "expected": str(versions.get("schema_version") or ""),
                    "actual": schema_version,
                }
            )
    if registry_path.is_file():
        registry = read_json(registry_path)
        registry_version = str(registry.get("registry_version") or "")
        if registry_version and registry_version != versions.get("registry_version"):
            version_drifts.append(
                {
                    "field": "registry_version",
                    "expected": str(versions.get("registry_version") or ""),
                    "actual": registry_version,
                }
            )
        profiles = registry.get("profiles") or []
        prompt_versions = {
            str(row.get("prompt_version"))
            for row in profiles
            if isinstance(row, dict) and row.get("prompt_version")
        }
        expected_prompt = str(versions.get("prompt_version") or "")
        if expected_prompt and prompt_versions and expected_prompt not in prompt_versions:
            version_drifts.append(
                {
                    "field": "prompt_version",
                    "expected": expected_prompt,
                    "actual": ",".join(sorted(prompt_versions)),
                }
            )

    ok = not drifts and not version_drifts
    return {
        "schema_version": "glitch.topstep.frozen_cohort_verify.v1",
        "manifest_path": str(manifest_path),
        "ok": ok,
        "file_hash_drifts": drifts,
        "version_drifts": version_drifts,
        "checked_files": checked,
        "frozen_versions": versions,
        "collection_queue_count": len(manifest.get("collection_queue") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify frozen cohort manifest file hashes")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to frozen-cohort-manifest JSON",
    )
    parser.add_argument("--repo-root", default=str(REPO))
    args = parser.parse_args()

    report = verify_frozen_cohort(
        manifest_path=Path(args.manifest),
        repo_root=Path(args.repo_root),
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
