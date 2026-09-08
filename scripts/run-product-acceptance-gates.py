#!/usr/bin/env python3
"""Aggregate product acceptance gates across profile + gateway with explicit classifications."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
REPORT_SCHEMA = "glitch.topstep.product_acceptance_report.v1"

PASS = "PASS"
FAIL_CODE = "FAIL_CODE"
BLOCKED_OPERATIONAL = "BLOCKED_OPERATIONAL"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
NOT_APPLICABLE = "NOT_APPLICABLE"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gateway_root() -> Path | None:
    env = os.environ.get("GLITCH_GATEWAY_ROOT", "").strip()
    if env:
        p = Path(env)
        return p if p.is_dir() else None
    sibling = REPO.parent / "glitch-topstep"
    return sibling if sibling.is_dir() else None


@dataclass
class CheckSpec:
    check_id: str
    phase: str
    category: str
    description: str
    command: list[str] | None = None
    cwd: Path | None = None
    fixed_classification: str | None = None
    fixed_detail: str | None = None
    timeout_s: float = 600.0


def _run_command(spec: CheckSpec) -> dict[str, Any]:
    if spec.fixed_classification:
        return {
            "check_id": spec.check_id,
            "phase": spec.phase,
            "category": spec.category,
            "description": spec.description,
            "classification": spec.fixed_classification,
            "detail": spec.fixed_detail,
            "duration_s": 0.0,
            "exit_code": None,
        }
    if spec.command is None:
        return {
            "check_id": spec.check_id,
            "phase": spec.phase,
            "category": spec.category,
            "description": spec.description,
            "classification": FAIL_CODE,
            "detail": "missing_command",
            "duration_s": 0.0,
            "exit_code": None,
        }
    cwd = spec.cwd or REPO
    started = time.monotonic()
    env = os.environ.copy()
    if cwd.resolve() == REPO.resolve():
        prefix = str(SCRIPTS)
        env["PYTHONPATH"] = prefix if not env.get("PYTHONPATH") else f"{prefix}{os.pathsep}{env['PYTHONPATH']}"
        env.setdefault("GLITCH_HERMES_PROFILE_ROOT", str(REPO))
    try:
        proc = subprocess.run(
            spec.command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            check=False,
            env=env,
        )
        duration = time.monotonic() - started
        if proc.returncode == 0:
            classification = PASS
            detail = (proc.stdout or "").strip()[-500:] or "ok"
        else:
            classification = FAIL_CODE
            detail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-2000:] or f"exit_{proc.returncode}"
        return {
            "check_id": spec.check_id,
            "phase": spec.phase,
            "category": spec.category,
            "description": spec.description,
            "classification": classification,
            "detail": detail,
            "duration_s": round(duration, 3),
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "check_id": spec.check_id,
            "phase": spec.phase,
            "category": spec.category,
            "description": spec.description,
            "classification": FAIL_CODE,
            "detail": f"subprocess_timeout:{spec.timeout_s}s",
            "duration_s": round(time.monotonic() - started, 3),
            "exit_code": None,
        }
    except FileNotFoundError as exc:
        return {
            "check_id": spec.check_id,
            "phase": spec.phase,
            "category": spec.category,
            "description": spec.description,
            "classification": BLOCKED_EXTERNAL,
            "detail": str(exc),
            "duration_s": round(time.monotonic() - started, 3),
            "exit_code": None,
        }


def build_checks(gw: Path | None) -> list[CheckSpec]:
    py = sys.executable
    checks: list[CheckSpec] = [
        CheckSpec("profile_quality", "evaluation_offline", "offline_test", "Profile syntax + regression presence", [py, str(SCRIPTS / "check_profile_quality.py")]),
        CheckSpec("profile_unittest_full", "evaluation_offline", "offline_test", "Full profile unittest discover", [py, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], timeout_s=300.0),
        CheckSpec("ensemble_evaluation", "evaluation_offline", "offline_test", "Ensemble evaluation gate", [py, "-m", "unittest", "tests.test_ensemble_evaluation", "-q"]),
        CheckSpec("six_profile_milestone", "evaluation_offline", "offline_test", "Six-profile milestone offline", [py, "-m", "unittest", "tests.test_expanded_evaluation_milestone", "-q"]),
        CheckSpec("wave5_sample_gate", "evaluation_offline", "offline_test", "Wave 5 measurement ready gate", [py, "-m", "unittest", "tests.test_evaluation_measurement_ready", "-q"]),
        CheckSpec("paired_contract", "evaluation_offline", "offline_test", "Paired contract profile", [py, "-m", "unittest", "tests.test_paired_contract", "tests.test_paired_contracts", "-q"]),
        CheckSpec("delivery_complete", "delivery_complete", "offline_test", "Coherent delivery_complete capture", [py, "-m", "unittest", "tests.test_coherent_evaluation_capture", "-q"]),
        CheckSpec("stability_gate_unit", "stability", "offline_test", "Operational stability gate unit tests", [py, "-m", "unittest", "tests.test_operational_stability_gate", "-q"]),
        CheckSpec("lease_coordination", "evaluation_offline", "offline_test", "Evaluation lease", [py, "-m", "unittest", "tests.test_evaluation_lease", "-q"]),
        CheckSpec("process_identity", "evaluation_offline", "offline_test", "Model owner lock / process identity", [py, "-m", "unittest", "tests.test_model_owner_lock", "-q"]),
        CheckSpec("shadow_offline_zero_write", "shadow", "offline_test", "Shadow phase7 offline + zero-write", [py, "-m", "unittest", "tests.test_shadow_phase7", "-q"]),
        CheckSpec("sha256_package", "evaluation_offline", "offline_test", "SHA256SUMS integrity", [py, "-m", "unittest", "tests.test_sha256sums", "-q"]),
        CheckSpec(
            "release_package",
            "evaluation_offline",
            "offline_test",
            "Six-profile release package validation",
            [py, str(SCRIPTS / "build-evaluation-release-package.py"), "--package-id", "six-profile-evaluation-package-2026-09-02"],
        ),
        CheckSpec("fault_injection_profile", "evaluation_offline", "offline_test", "Profile fault injection", [py, "-m", "unittest", "tests.test_fault_injection", "-q"]),
        CheckSpec(
            "stability_live_v6",
            "stability",
            "live_test",
            "Bar-close-aware stability window (v6)",
            fixed_classification=BLOCKED_OPERATIONAL,
            fixed_detail="v5 FAIL preserved; v6 blocked until gateway PR #264 merge + CI green",
        ),
        CheckSpec(
            "prac_spontaneous",
            "prac",
            "live_test",
            "PRAC spontaneous capture",
            fixed_classification=BLOCKED_OPERATIONAL,
            fixed_detail="Blocked until v6 stability PASS",
        ),
        CheckSpec(
            "soak_72h",
            "soak_72h",
            "live_test",
            "Evaluation soak 72h parallel",
            fixed_classification=BLOCKED_OPERATIONAL,
            fixed_detail="Blocked until PRAC first valid spontaneous cycle",
        ),
        CheckSpec(
            "shadow_live_001",
            "shadow",
            "live_test",
            "Shadow live read-only 001",
            fixed_classification=BLOCKED_OPERATIONAL,
            fixed_detail="Blocked until evaluation soak review",
        ),
        CheckSpec(
            "paper_controlled",
            "paper",
            "live_test",
            "Paper live controlled",
            fixed_classification=NOT_APPLICABLE,
            fixed_detail="Lane not opened; requires shadow 001/002/003 PASS",
        ),
        CheckSpec(
            "canary",
            "canary",
            "live_test",
            "Canary promotion",
            fixed_classification=NOT_APPLICABLE,
            fixed_detail="Future lane — not in scope",
        ),
        CheckSpec(
            "armed_production",
            "armed_production",
            "live_test",
            "Armed production promotion",
            fixed_classification=NOT_APPLICABLE,
            fixed_detail="Requires canary + human sign-off",
        ),
        CheckSpec(
            "historical_memory_error_gate",
            "stability",
            "historical_artifact",
            "Pre-ef70bbc MemoryError hang (artefact only)",
            fixed_classification=NOT_APPLICABLE,
            fixed_detail="test_timeout_blocked_bar_close_window ~54min hang before #220; do not use for ef70bbc gate",
        ),
    ]
    if gw is None:
        checks.extend([
            CheckSpec("gateway_check", "evaluation_offline", "offline_test", "Gateway npm run check", fixed_classification=BLOCKED_EXTERNAL, fixed_detail="gateway repo not found (set GLITCH_GATEWAY_ROOT)"),
            CheckSpec("gateway_packet_timeout", "stability", "offline_test", "Packet observation refresh bounded", fixed_classification=BLOCKED_EXTERNAL, fixed_detail="gateway repo not found"),
            CheckSpec("gateway_quote_geometry", "stability", "offline_test", "quote_geometry_invalid classification", fixed_classification=BLOCKED_EXTERNAL, fixed_detail="gateway repo not found"),
            CheckSpec("fault_matrix", "evaluation_offline", "offline_test", "Cross-repo fault matrix", fixed_classification=BLOCKED_EXTERNAL, fixed_detail="gateway repo not found"),
            CheckSpec("gateway_sibling_prac_chain", "prac", "offline_test", "validate-prac-evidence-chain sibling", fixed_classification=BLOCKED_EXTERNAL, fixed_detail="gateway repo not found"),
        ])
    else:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        checks.extend([
            CheckSpec("gateway_check", "evaluation_offline", "offline_test", "Gateway npm run check", [npm, "run", "check"], cwd=gw, timeout_s=180.0),
            CheckSpec(
                "gateway_packet_timeout",
                "stability",
                "offline_test",
                "Packet observation refresh bounded (build + unit)",
                [npm, "run", "build"],
                cwd=gw,
                timeout_s=120.0,
            ),
            CheckSpec(
                "gateway_quote_geometry",
                "stability",
                "offline_test",
                "quote_geometry_invalid unit test",
                ["node", "--test", "dist/tests/data-quality.test.js"], cwd=gw, timeout_s=60.0,
            ),
            CheckSpec("fault_matrix", "evaluation_offline", "offline_test", "Cross-repo fault matrix", [npm, "run", "reaudit:fault-matrix"], cwd=gw, timeout_s=120.0),
        ])
        prac_chain = gw / "scripts" / "validate-prac-evidence-chain.py"
        prep = gw / "scripts" / "run-prac-prep-check.ps1"
        if prac_chain.is_file():
            checks.append(CheckSpec("gateway_sibling_prac_chain", "prac", "offline_test", "validate-prac-evidence-chain example", [py, str(prac_chain), "--example"], cwd=gw))
        else:
            checks.append(CheckSpec("gateway_sibling_prac_chain", "prac", "offline_test", "validate-prac-evidence-chain", fixed_classification=BLOCKED_EXTERNAL, fixed_detail=f"missing:{prac_chain}"))
        if not prep.is_file():
            checks.append(CheckSpec("gateway_prac_prep_script", "prac", "offline_test", "run-prac-prep-check.ps1", fixed_classification=BLOCKED_EXTERNAL, fixed_detail=f"missing:{prep}"))
    # packet timeout unit test (after build in gateway_packet_timeout - chain separately)
    if gw is not None:
        checks.append(CheckSpec(
            "gateway_packet_timeout_unit",
            "stability",
            "offline_test",
            "boundedPacketObservationRefresh tests",
            ["node", "--test", "dist/tests/packet-observation-refresh.test.js"],
            cwd=gw,
            timeout_s=60.0,
        ))
        checks.append(CheckSpec(
            "health_packet_divergence_unit",
            "stability",
            "offline_test",
            "Health/packet reconcile coherence",
            ["node", "--test", "dist/tests/reconciliation-account-freshness.test.js"],
            cwd=gw,
            timeout_s=60.0,
        ))
    return checks


def summarize_phase(results: list[dict[str, Any]], phase_id: str) -> dict[str, Any]:
    phase_rows = [r for r in results if r["phase"] == phase_id]
    counts = {c: 0 for c in (PASS, FAIL_CODE, BLOCKED_OPERATIONAL, BLOCKED_EXTERNAL, NOT_APPLICABLE)}
    for row in phase_rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    applicable = [r for r in phase_rows if r["classification"] not in (NOT_APPLICABLE,)]
    pass_count = sum(1 for r in applicable if r["classification"] == PASS)
    pct = round(100.0 * pass_count / len(applicable), 1) if applicable else None
    blocked = any(r["classification"] in (BLOCKED_OPERATIONAL, BLOCKED_EXTERNAL) for r in phase_rows)
    failed = any(r["classification"] == FAIL_CODE for r in phase_rows)
    if failed:
        phase_verdict = FAIL_CODE
    elif blocked and pass_count < len([r for r in applicable if r["classification"] != BLOCKED_EXTERNAL]):
        phase_verdict = BLOCKED_OPERATIONAL if any(r["classification"] == BLOCKED_OPERATIONAL for r in phase_rows) else BLOCKED_EXTERNAL
    elif applicable and pass_count == len(applicable):
        phase_verdict = PASS
    else:
        phase_verdict = BLOCKED_OPERATIONAL
    return {
        "phase_id": phase_id,
        "checks": len(phase_rows),
        "counts": counts,
        "pass_pct_applicable": pct,
        "verdict": phase_verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run product acceptance gate matrix")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--skip-slow", action="store_true", help="Skip profile_unittest_full and gateway_check")
    args = parser.parse_args()

    gw = gateway_root()
    matrix_path = REPO / "evaluation" / "acceptance-matrix.v1.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8")) if matrix_path.is_file() else {}

    specs = build_checks(gw)
    if args.skip_slow:
        skip_ids = {"profile_unittest_full", "gateway_check"}
        specs = [s for s in specs if s.check_id not in skip_ids]

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
        futures = {pool.submit(_run_command, spec): spec for spec in specs}
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: r["check_id"])

    phases = matrix.get("pipeline_order") or []
    phase_summary = [summarize_phase(results, pid) for pid in phases]

    by_category: dict[str, list[str]] = {}
    for row in results:
        by_category.setdefault(row["category"], []).append(row["check_id"])

    report = {
        "schema_version": REPORT_SCHEMA,
        "generated_utc": utc_now(),
        "repos": {
            "profile_root": str(REPO),
            "gateway_root": str(gw) if gw else None,
        },
        "matrix_path": str(matrix_path),
        "checks": results,
        "phase_summary": phase_summary,
        "sections": {
            "offline_tests": [r for r in results if r["category"] == "offline_test"],
            "live_tests": [r for r in results if r["category"] == "live_test"],
            "operational_blocks": [r for r in results if r["classification"] == BLOCKED_OPERATIONAL],
            "external_blocks": [r for r in results if r["classification"] == BLOCKED_EXTERNAL],
            "code_failures": [r for r in results if r["classification"] == FAIL_CODE],
            "historical_artifacts": [r for r in results if r["category"] == "historical_artifact"],
        },
        "next_gate": "v6_stability_after_gateway_pr_264_merge",
        "commits_prs": {
            "profile_stability_gate": "ef70bbc (#220 merged)",
            "gateway_packet_budget": "PR #264 fix/packet-observation-refresh-budget (pending Security Reviewer)",
            "v5_evidence": "docs/evidence/gateway-diagnosis/2026-09-08-bar-close-aware-stability-v5/",
        },
    }

    out = args.output or (REPO / "evaluation" / "runs" / f"product-acceptance-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "report_path": str(out),
        "phase_summary": phase_summary,
        "failures": len(report["sections"]["code_failures"]),
        "operational_blocks": len(report["sections"]["operational_blocks"]),
        "external_blocks": len(report["sections"]["external_blocks"]),
    }, indent=2))

    if report["sections"]["code_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
