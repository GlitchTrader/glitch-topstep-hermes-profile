"""Build frozen six-profile evaluation release package with hashes and safety flags."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
PACKAGE_SCHEMA = "glitch.topstep.six_profile_evaluation_package.v1"

PINNED_PATHS = (
    "evaluation/registry.json",
    "evaluation/capability-matrix.json",
    "evaluation/ensemble_config.json",
    "evaluation/aggregator_rules.v1.json",
    "evaluation/evaluation_output_contract.v1.json",
    "evaluation/packet_envelope_mapping.v1.json",
    "evaluation/shadow-live-run-config.v1.json",
    "evaluation/shadow-live-scenarios.v1.json",
    "evaluation/profiles/smart-money.v1.json",
    "evaluation/profiles/indicators.v1.json",
    "evaluation/profiles/orderflow.v1.json",
    "scripts/shadow-preflight.py",
    "scripts/shadow-observe-offline.py",
    "scripts/shadow-observe-live.py",
    "scripts/shadow_gateway_readonly.py",
    "scripts/shadow_modes.py",
    "scripts/shadow_observation.py",
    "scripts/run-parallel-ensemble-evaluation.py",
    "scripts/ensemble_aggregator.py",
    "scripts/ensemble_parallel_runner.py",
    "scripts/evaluation-measurement-ready.py",
    "scripts/build-evaluation-release-package.py",
    "scripts/report-shadow-metrics.py",
    "scripts/audit-shadow-isolation.py",
    "scripts/run-shadow-phase7-validation.py",
)

SCHEMA_PATHS = (
    "evaluation/schemas/evaluation_envelope.v1.json",
    "evaluation/schemas/normalized_candidate.v1.json",
    "evaluation/schemas/ensemble_selection.v1.json",
    "evaluation/schemas/shadow_observation.v1.json",
    "evaluation/schemas/shadow_preflight.v1.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_release_package(*, package_id: str) -> dict[str, Any]:
    registry = _read_json(REPO / "evaluation/registry.json")
    matrix = _read_json(REPO / "evaluation/capability-matrix.json")
    ensemble = _read_json(REPO / "evaluation/ensemble_config.json")
    rules = _read_json(REPO / "evaluation/aggregator_rules.v1.json")

    profiles = [p for p in registry.get("profiles") or [] if p.get("enabled", True)]
    exec_auth_ok = all(not p.get("execution_authority", False) for p in profiles)
    eval_enabled_ok = all(p.get("evaluation_enabled") for p in profiles)

    file_hashes: dict[str, str] = {}
    missing: list[str] = []
    for rel in list(PINNED_PATHS) + list(SCHEMA_PATHS):
        path = REPO / rel
        if not path.is_file():
            missing.append(rel)
            continue
        file_hashes[rel] = _sha256_file(path)

    gateway_repo = REPO.parent / "glitch-topstep"
    paired_contract: dict[str, Any] | None = None
    paired_path = gateway_repo / "release" / "paired-contract.json"
    if paired_path.is_file():
        paired_contract = _read_json(paired_path)

    prompt_versions = sorted({str(p.get("prompt_version") or "") for p in profiles if p.get("prompt_version")})

    return {
        "schema_version": PACKAGE_SCHEMA,
        "package_id": package_id,
        "generated_utc": utc_now(),
        "profile_count": len(profiles),
        "profile_ids": [str(p["profile_id"]) for p in profiles],
        "versions": {
            "registry_version": registry.get("registry_version"),
            "capability_matrix_version": matrix.get("matrix_version"),
            "config_version": ensemble.get("config_version"),
            "aggregator_rules_version": rules.get("rules_version"),
            "prompt_versions": prompt_versions,
        },
        "safety_flags": {
            "execution_authority_false_all": exec_auth_ok,
            "evaluation_enabled_all": eval_enabled_ok,
            "production_parallelism": "blocked",
            "promotion_use_allowed": False,
            "shadow_live_execution_authorized": False,
            "intents_sent": 0,
            "orders_sent": 0,
            "writes_operacionais": 0,
        },
        "git_commits": {
            "profile_repo": _git_head(REPO),
            "gateway_repo": _git_head(gateway_repo) if gateway_repo.is_dir() else None,
        },
        "paired_contract": {
            "gateway_version": (paired_contract or {}).get("gateway", {}).get("version"),
            "profile_version": (paired_contract or {}).get("profile", {}).get("version"),
            "prompt_version": (paired_contract or {}).get("profile", {}).get("prompt_version"),
            "protocol_revision": (paired_contract or {}).get("protocol_revision"),
        }
        if paired_contract
        else None,
        "file_hashes": file_hashes,
        "missing_files": missing,
        "valid": exec_auth_ok and eval_enabled_ok and len(missing) == 0 and len(profiles) == 6,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build six-profile evaluation release package")
    parser.add_argument("--package-id", default="six-profile-evaluation-package-2026-09-02")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "evaluation" / "release" / "six-profile-evaluation-package-2026-09-02.json",
    )
    args = parser.parse_args()

    package = build_release_package(package_id=args.package_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": package["valid"], "output": str(args.output)}, indent=2))
    return 0 if package["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
