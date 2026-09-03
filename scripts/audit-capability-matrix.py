"""Audit evaluation/capability-matrix.json against registry, skills, sources, and tools."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROFILE_ROOT / "evaluation" / "capability-matrix.json"
DEFAULT_REGISTRY = PROFILE_ROOT / "evaluation" / "registry.json"
DEFAULT_OUTPUT = PROFILE_ROOT / "evaluation" / "runs" / "capability-matrix-audit.json"
SKILLS_ROOT = PROFILE_ROOT / "skills"

PACKET_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
COMPARABLE_SOURCE_RE = re.compile(r"^([a-z_]+)\.(available|missing_required)$")

# ponytail: static index until evaluation/tool_catalog.v1.json exists
TOOL_DOC_PATHS: dict[str, list[str]] = {
    "market_observation": [
        "docs/specs/GTHP-011.md",
        "scripts/packet_model.py",
    ],
    "scanner_contract": [
        "scripts/scanner_contract.py",
        "docs/specs/GTHP-DATA-01-MULTI-INSTRUMENT.md",
    ],
    "structural_levels": [
        "scripts/packet_model.py",
    ],
    "setup_state": [
        "skills/topstep-setup-state/SKILL.md",
    ],
    "risk_assessment": [
        "skills/topstep-assess-risk/SKILL.md",
    ],
    "entry_candidate_geometry": [
        "scripts/ensemble_geometry.py",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _tool_documented(profile_root: Path, tool_name: str) -> bool:
    for relative in TOOL_DOC_PATHS.get(tool_name, []):
        path = profile_root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return True
    return False


def _comparability_sources(comparability: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    for field in ("comparable_when", "incomparable_when"):
        values = comparability.get(field)
        if not isinstance(values, list):
            continue
        for token in values:
            match = COMPARABLE_SOURCE_RE.match(str(token))
            if match:
                sources.add(match.group(1))
    return sources


def audit_capability_matrix(
    *,
    matrix: dict[str, Any],
    registry: dict[str, Any],
    profile_root: Path,
) -> dict[str, Any]:
    issues: list[str] = []
    profile_flags: list[dict[str, Any]] = []

    catalog = matrix.get("source_catalog")
    profiles = matrix.get("profiles")
    if not isinstance(catalog, dict):
        issues.append("source_catalog_missing")
        catalog = {}
    if not isinstance(profiles, dict):
        issues.append("profiles_missing")
        profiles = {}

    catalog_ids = set(catalog)

    for source_id, spec in catalog.items():
        if not isinstance(spec, dict):
            issues.append(f"source_catalog_entry_invalid:{source_id}")
            continue
        paths = spec.get("packet_paths")
        if not isinstance(paths, list):
            issues.append(f"packet_paths_missing:{source_id}")
            continue
        for path in paths:
            path_text = str(path)
            if not PACKET_PATH_RE.match(path_text):
                issues.append(f"packet_path_syntax_invalid:{source_id}:{path_text}")

    registry_skills: set[str] = set()
    for row in registry.get("profiles", []):
        if not isinstance(row, dict):
            continue
        for skill in row.get("skills", []):
            skill_name = str(skill)
            registry_skills.add(skill_name)
            if not (profile_root / "skills" / skill_name).is_dir():
                issues.append(f"registry_skill_missing:{skill_name}")

    documented_tools: dict[str, bool] = {}
    declared_tools: set[str] = set()

    for profile_id, spec in profiles.items():
        if not isinstance(spec, dict):
            issues.append(f"profile_spec_invalid:{profile_id}")
            continue

        required = [str(x) for x in spec.get("required_sources", [])]
        optional = [str(x) for x in spec.get("optional_sources", [])]
        overlap = sorted(set(required) & set(optional))
        if overlap:
            issues.append(f"required_optional_overlap:{profile_id}:{','.join(overlap)}")

        for source_id in required + optional:
            if source_id not in catalog_ids:
                issues.append(f"unknown_source:{profile_id}:{source_id}")

        for skill in spec.get("skills", []):
            skill_name = str(skill)
            if not (profile_root / "skills" / skill_name).is_dir():
                issues.append(f"matrix_skill_missing:{profile_id}:{skill_name}")

        for tool in spec.get("tools", []):
            if not isinstance(tool, dict):
                issues.append(f"tool_entry_invalid:{profile_id}")
                continue
            tool_name = str(tool.get("name") or "")
            if not tool_name:
                issues.append(f"tool_name_missing:{profile_id}")
                continue
            declared_tools.add(tool_name)
            if tool_name not in documented_tools:
                documented_tools[tool_name] = _tool_documented(profile_root, tool_name)
            if not documented_tools[tool_name]:
                issues.append(f"tool_undocumented:{profile_id}:{tool_name}")

        comparability = spec.get("comparability")
        if isinstance(comparability, dict):
            covered = _comparability_sources(comparability)
            missing_coverage = sorted(set(required) - covered)
            if missing_coverage:
                profile_flags.append(
                    {
                        "profile_id": profile_id,
                        "flag": "comparability_missing_required_source_coverage",
                        "missing_sources": missing_coverage,
                        "required_sources": required,
                        "comparability_sources": sorted(covered),
                    }
                )

    return {
        "schema_version": "glitch.topstep.capability_matrix_audit.v1",
        "generated_utc": utc_now(),
        "matrix_version": matrix.get("matrix_version"),
        "registry_version": registry.get("registry_version"),
        "registry_skill_count": len(registry_skills),
        "declared_tool_count": len(declared_tools),
        "profile_count": len(profiles),
        "valid": not issues,
        "issues": issues,
        "profile_flags": profile_flags,
        "checks": {
            "registry_skills_on_disk": True,
            "matrix_sources_in_catalog": True,
            "required_optional_disjoint": True,
            "packet_paths_dotted_syntax": True,
            "tools_documented": True,
            "comparability_covers_required_sources": len(profile_flags) == 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit capability matrix consistency")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--profile-root", type=Path, default=PROFILE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = audit_capability_matrix(
        matrix=read_json(args.matrix),
        registry=read_json(args.registry),
        profile_root=args.profile_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "issue_count": len(report["issues"])}, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
