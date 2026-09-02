"""Audit evaluation/registry.json — skills, refs, promotion, ensemble compatibility."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROFILE_ROOT / "evaluation" / "registry.json"
DEFAULT_MATRIX = PROFILE_ROOT / "evaluation" / "capability-matrix.json"
DEFAULT_OUTPUT = PROFILE_ROOT / "evaluation" / "runs" / "profile-registry-audit.json"
DEFAULT_OUTPUT_CONTRACT = PROFILE_ROOT / "evaluation" / "evaluation_output_contract.v1.json"
DEFAULT_PAIRED_CONTRACT = PROFILE_ROOT / "paired-contract.json"
SKILLS_ROOT = PROFILE_ROOT / "skills"
DOCS_OPERATIONS = PROFILE_ROOT / "docs" / "OPERATIONS.md"

EVIDENCE_REF_RE = re.compile(
    r"^evaluation/capability-matrix\.json#profiles\.([A-Za-z0-9_-]+)$"
)
ENSEMBLE_RUN_GLOBS = (
    "scenario-live-2026-09-01-r7-contract.json",
    "scenario-live-2026-09-01-r8-contract.json",
    "scenario-live-2026-09-01-r9-v2.json",
)
REGISTRY_MANIFEST_KEYS = frozenset({
    "profile_id",
    "profile_version",
    "profile_kind",
    "prompt_version",
    "skills",
    "enabled",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _registry_manifest(registry: dict[str, Any]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for row in registry.get("profiles", []):
        if not isinstance(row, dict):
            continue
        manifest.append({
            "profile_id": row.get("profile_id"),
            "profile_version": row.get("profile_version"),
            "profile_kind": row.get("profile_kind"),
            "prompt_version": row.get("prompt_version"),
            "skills": list(row.get("skills") or []),
            "enabled": row.get("enabled", True),
        })
    return manifest


def _artifact_basename(artifact_path: str) -> str:
    return Path(str(artifact_path).replace("\\", "/")).name


def _load_ensemble_artifacts(runs_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ENSEMBLE_RUN_GLOBS:
        bundle_path = runs_dir / name
        if not bundle_path.is_file():
            continue
        bundle = read_json(bundle_path)
        for inv in bundle.get("invocations") or []:
            artifact_path = inv.get("artifact_path")
            if not artifact_path:
                continue
            path = Path(str(artifact_path).replace("\\", "/"))
            if not path.is_file():
                path = runs_dir / _artifact_basename(str(artifact_path))
            if path.is_file():
                doc = read_json(path)
                if doc.get("schema_version") == "glitch.topstep.minimal_cognitive_replay.v1":
                    rows.append(doc)
    return rows


def audit_profile_registry(
    *,
    registry: dict[str, Any],
    matrix: dict[str, Any],
    profile_root: Path,
    output_contract: dict[str, Any],
    paired_contract: dict[str, Any] | None = None,
    runs_dir: Path | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    profile_checks: list[dict[str, Any]] = []

    if registry.get("promotion_status") != "blocked":
        issues.append(f"promotion_status_not_blocked:{registry.get('promotion_status')}")

    execution_mode = str(registry.get("execution_mode") or "")
    allowed_modes = {"offline_sequential", "offline_parallel_evaluation"}
    if execution_mode not in allowed_modes:
        issues.append(f"execution_mode_unexpected:{execution_mode}")

    if registry.get("evaluation_only") is not True:
        issues.append("evaluation_only_not_true")

    matrix_profiles = matrix.get("profiles")
    if not isinstance(matrix_profiles, dict):
        issues.append("capability_matrix_profiles_missing")
        matrix_profiles = {}

    matrix_version = str(registry.get("capability_matrix_version") or "")
    if matrix_version and matrix.get("matrix_version") != matrix_version:
        issues.append(
            f"capability_matrix_version_mismatch:registry={matrix_version},"
            f"matrix={matrix.get('matrix_version')}"
        )

    contract_path = profile_root / "evaluation" / "evaluation_output_contract.v1.json"
    if not contract_path.is_file():
        issues.append("output_contract_missing")
    elif output_contract.get("schema_version") != "glitch.topstep.evaluation_output_contract.v1":
        issues.append("output_contract_schema_invalid")

    canonical_prompt = None
    if paired_contract:
        profile_block = paired_contract.get("profile") or {}
        canonical_prompt = str(profile_block.get("prompt_version") or "") or None

    ops_text = ""
    if DOCS_OPERATIONS.is_file():
        ops_text = DOCS_OPERATIONS.read_text(encoding="utf-8", errors="replace")

    enabled_profiles: list[str] = []
    registry_prompt_versions: set[str] = set()

    for row in registry.get("profiles") or []:
        if not isinstance(row, dict):
            issues.append("registry_profile_row_invalid")
            continue

        profile_id = str(row.get("profile_id") or "")
        if not profile_id:
            issues.append("profile_id_missing")
            continue

        enabled = row.get("enabled", True)
        if enabled:
            enabled_profiles.append(profile_id)

        prompt_version = str(row.get("prompt_version") or "")
        if not prompt_version:
            issues.append(f"prompt_version_missing:{profile_id}")
        else:
            registry_prompt_versions.add(prompt_version)
            if canonical_prompt and prompt_version != canonical_prompt:
                issues.append(
                    f"prompt_version_paired_contract_mismatch:{profile_id}:"
                    f"{prompt_version}!={canonical_prompt}"
                )
            documented = (
                prompt_version in ops_text
                or "PROMPT_VERSION" in ops_text
                or (canonical_prompt and prompt_version == canonical_prompt)
            )
            if not documented:
                issues.append(f"prompt_version_not_documented:{profile_id}")

        skills = [str(s) for s in row.get("skills") or []]
        missing_skills = [
            skill for skill in skills if not (profile_root / "skills" / skill).is_dir()
        ]
        for skill in missing_skills:
            issues.append(f"skill_missing_on_disk:{profile_id}:{skill}")

        evidence_ref = str(row.get("evidence_requirements_ref") or "")
        matrix_profile_id = None
        match = EVIDENCE_REF_RE.match(evidence_ref)
        if not match:
            issues.append(f"evidence_requirements_ref_invalid:{profile_id}:{evidence_ref}")
        else:
            matrix_profile_id = match.group(1)
            if matrix_profile_id != profile_id:
                issues.append(
                    f"evidence_requirements_ref_profile_mismatch:{profile_id}:{matrix_profile_id}"
                )
            if matrix_profile_id not in matrix_profiles:
                issues.append(f"capability_matrix_profile_missing:{matrix_profile_id}")

        profile_checks.append({
            "profile_id": profile_id,
            "enabled": enabled,
            "prompt_version": prompt_version or None,
            "skills_count": len(skills),
            "skills_on_disk": len(missing_skills) == 0,
            "evidence_requirements_ref": evidence_ref or None,
            "capability_matrix_resolves": matrix_profile_id in matrix_profiles if matrix_profile_id else False,
        })

    if len(registry_prompt_versions) > 1:
        issues.append(f"prompt_version_inconsistent_across_profiles:{sorted(registry_prompt_versions)}")

    manifest = _registry_manifest(registry)
    ensemble_compat: dict[str, Any] = {"artifact_count": 0, "mismatches": []}
    runs_path = runs_dir or (profile_root / "evaluation" / "runs")
    artifacts = _load_ensemble_artifacts(runs_path)
    ensemble_compat["artifact_count"] = len(artifacts)

    registry_by_id = {str(r["profile_id"]): r for r in manifest}
    for artifact in artifacts:
        profile_id = str(artifact.get("profile_id") or "")
        reg_row = registry_by_id.get(profile_id)
        if reg_row is None:
            ensemble_compat["mismatches"].append({
                "run_id": artifact.get("run_id"),
                "kind": "unknown_profile",
                "profile_id": profile_id,
            })
            issues.append(f"ensemble_artifact_unknown_profile:{profile_id}")
            continue
        if not reg_row.get("enabled"):
            issues.append(f"ensemble_artifact_disabled_profile:{profile_id}")
        art_prompt = str(artifact.get("prompt_version") or "")
        reg_prompt = str(reg_row.get("prompt_version") or "")
        if art_prompt and reg_prompt and art_prompt != reg_prompt:
            ensemble_compat["mismatches"].append({
                "run_id": artifact.get("run_id"),
                "kind": "prompt_version",
                "artifact": art_prompt,
                "registry": reg_prompt,
            })
            issues.append(f"ensemble_prompt_version_mismatch:{profile_id}:{art_prompt}!={reg_prompt}")
        art_skills = set(artifact.get("skills") or [])
        reg_skills = set(reg_row.get("skills") or [])
        if art_skills and reg_skills and art_skills != reg_skills:
            ensemble_compat["mismatches"].append({
                "run_id": artifact.get("run_id"),
                "kind": "skills",
                "artifact": sorted(art_skills),
                "registry": sorted(reg_skills),
            })
            issues.append(f"ensemble_skills_mismatch:{profile_id}")

    return {
        "schema_version": "glitch.topstep.profile_registry_audit.v1",
        "generated_utc": utc_now(),
        "registry_version": registry.get("registry_version"),
        "registry_path": "evaluation/registry.json",
        "output_contract_ref": "evaluation/evaluation_output_contract.v1.json",
        "output_contract_version": output_contract.get("contract_version"),
        "valid": not issues,
        "issues": issues,
        "checks": {
            "promotion_status_blocked": registry.get("promotion_status") == "blocked",
            "execution_mode_offline_sequential": execution_mode == "offline_sequential",
            "execution_mode_offline_parallel_evaluation": execution_mode == "offline_parallel_evaluation",
            "evaluation_only": registry.get("evaluation_only") is True,
            "output_contract_exists": contract_path.is_file(),
            "capability_matrix_version_aligned": matrix_version == matrix.get("matrix_version"),
            "all_skills_on_disk": not any(i.startswith("skill_missing_on_disk:") for i in issues),
            "prompt_version_documented": not any(
                i.startswith("prompt_version_not_documented") for i in issues
            ),
            "enabled_profiles": enabled_profiles,
            "ensemble_manifest_compatible": len(ensemble_compat["mismatches"]) == 0,
        },
        "registry_manifest": manifest,
        "registry_manifest_keys": sorted(REGISTRY_MANIFEST_KEYS),
        "profiles": profile_checks,
        "ensemble_compatibility": ensemble_compat,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit evaluation registry consistency")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-contract", type=Path, default=DEFAULT_OUTPUT_CONTRACT)
    parser.add_argument("--paired-contract", type=Path, default=DEFAULT_PAIRED_CONTRACT)
    parser.add_argument("--profile-root", type=Path, default=PROFILE_ROOT)
    parser.add_argument("--runs-dir", type=Path, default=PROFILE_ROOT / "evaluation" / "runs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    paired = read_json(args.paired_contract) if args.paired_contract.is_file() else None
    report = audit_profile_registry(
        registry=read_json(args.registry),
        matrix=read_json(args.matrix),
        profile_root=args.profile_root,
        output_contract=read_json(args.output_contract),
        paired_contract=paired,
        runs_dir=args.runs_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "issue_count": len(report["issues"])}, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
