#!/usr/bin/env python3
"""Manifest-driven evaluation gate aggregator — offline + live lanes, no duplicate milestone runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
MANIFEST_PATH = REPO / "evaluation" / "gate-manifest.v1.json"
REPORT_SCHEMA = "glitch.topstep.gate_report.v1"

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
SKIP = "SKIP"
CONDITIONAL = "CONDITIONAL"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gateway_root() -> Path | None:
    env = os.environ.get("GLITCH_GATEWAY_ROOT", "").strip()
    if env:
        candidate = Path(env)
        return candidate if candidate.is_dir() else None
    sibling = REPO.parent / "glitch-topstep"
    return sibling if sibling.is_dir() else None


def git_sha(root: Path | None) -> str | None:
    if root is None or not (root / ".git").exists():
        return None
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or MANIFEST_PATH
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _resolve_command(command: list[str], *, run_id: str, python: str, npm: str) -> list[str]:
    resolved: list[str] = []
    for part in command:
        resolved.append(
            part.replace("{python}", python)
            .replace("{npm}", npm)
            .replace("{run_id}", run_id)
        )
    return resolved


def _gate_cwd(gate: dict[str, Any], gw: Path | None) -> Path:
    cwd_key = gate.get("cwd", "profile")
    if cwd_key == "gateway":
        if gw is None:
            raise FileNotFoundError("gateway repo not found (set GLITCH_GATEWAY_ROOT)")
        return gw
    return REPO


def _dependency_batches(gates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    by_id = {g["id"]: g for g in gates}
    remaining = {g["id"] for g in gates}
    batches: list[list[dict[str, Any]]] = []
    while remaining:
        ready = [
            gid
            for gid in remaining
            if all(dep not in remaining for dep in by_id[gid].get("depends_on", []))
        ]
        if not ready:
            raise ValueError(f"gate dependency cycle: {sorted(remaining)}")
        batches.append([by_id[gid] for gid in sorted(ready)])
        remaining -= set(ready)
    return batches


def _run_gate(
    gate: dict[str, Any],
    *,
    run_id: str,
    gw: Path | None,
    authorize_live: bool,
    artifact_dir: Path,
    prior: dict[str, dict[str, Any]],
    python: str,
    npm: str,
) -> dict[str, Any]:
    gate_id = gate["id"]
    started = time.monotonic()
    base: dict[str, Any] = {
        "gate_id": gate_id,
        "phase": gate.get("phase"),
        "mode": gate.get("mode"),
        "description": gate.get("description"),
        "depends_on": gate.get("depends_on", []),
        "duration_s": 0.0,
        "exit_code": None,
        "stdout_path": None,
        "stderr_path": None,
        "detail": None,
    }

    for dep in gate.get("depends_on", []):
        dep_result = prior.get(dep)
        if dep_result is None:
            base.update(status=BLOCKED, detail=f"dependency_missing:{dep}")
            base["duration_s"] = round(time.monotonic() - started, 3)
            return base
        if dep_result["status"] in {FAIL, BLOCKED}:
            base.update(status=BLOCKED, detail=f"dependency_{dep_result['status'].lower()}:{dep}")
            base["duration_s"] = round(time.monotonic() - started, 3)
            return base

    if gate.get("live_gate"):
        if not authorize_live:
            base.update(
                status=BLOCKED,
                detail=gate.get("blocked_detail") or "live_gate_requires_--authorize-live",
            )
            base["duration_s"] = round(time.monotonic() - started, 3)
            return base
        base.update(status=BLOCKED, detail="live_execution_not_implemented_in_offline_runner")
        base["duration_s"] = round(time.monotonic() - started, 3)
        return base

    if gate.get("requires_gateway") and gw is None:
        base.update(status=BLOCKED, detail="gateway_repo_not_found:set_GLITCH_GATEWAY_ROOT")
        base["duration_s"] = round(time.monotonic() - started, 3)
        return base

    command = gate.get("command")
    if not command:
        base.update(status=SKIP, detail="no_command")
        base["duration_s"] = round(time.monotonic() - started, 3)
        return base

    cwd = _gate_cwd(gate, gw)
    resolved = _resolve_command(list(command), run_id=run_id, python=python, npm=npm)
    stdout_path = artifact_dir / f"{gate_id}.stdout.log"
    stderr_path = artifact_dir / f"{gate_id}.stderr.log"
    base["stdout_path"] = str(stdout_path)
    base["stderr_path"] = str(stderr_path)

    env = os.environ.copy()
    env.setdefault("GLITCH_HERMES_PROFILE_ROOT", str(REPO))
    if gw is not None:
        env.setdefault("GLITCH_GATEWAY_ROOT", str(gw))
    if cwd == REPO:
        prefix = str(SCRIPTS)
        env["PYTHONPATH"] = prefix if not env.get("PYTHONPATH") else f"{prefix}{os.pathsep}{env['PYTHONPATH']}"

    try:
        proc = subprocess.run(
            resolved,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=float(gate.get("timeout_s", 600)),
            check=False,
            env=env,
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        base["exit_code"] = proc.returncode
        base["duration_s"] = round(time.monotonic() - started, 3)
        if proc.returncode == 0:
            base["status"] = PASS
            base["detail"] = (proc.stdout or "").strip()[-500:] or "ok"
        else:
            combined = ((proc.stderr or "") + (proc.stdout or "")).strip()
            if "WinError" in combined or "gateway_repo_not_found" in combined:
                base["status"] = CONDITIONAL
            else:
                base["status"] = FAIL
            base["detail"] = combined[-2000:] or f"exit_{proc.returncode}"
        return base
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + f"\nTIMEOUT after {gate.get('timeout_s')}s", encoding="utf-8")
        base.update(status=FAIL, detail=f"timeout:{gate.get('timeout_s')}s", exit_code=None)
        base["duration_s"] = round(time.monotonic() - started, 3)
        return base
    except FileNotFoundError as exc:
        base.update(status=BLOCKED, detail=str(exc))
        base["duration_s"] = round(time.monotonic() - started, 3)
        return base


def run_gates(
    *,
    run_id: str,
    manifest: dict[str, Any],
    gw: Path | None,
    authorize_live: bool = False,
    offline_only: bool = True,
    max_workers: int = 4,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    gates = list(manifest.get("gates") or [])
    if offline_only:
        gates = [g for g in gates if g.get("mode") == "offline"]
    artifact_dir = artifact_dir or (REPO / "evaluation" / "runs" / "gate-artifacts" / run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    npm = "npm.cmd" if os.name == "nt" else "npm"
    results: dict[str, dict[str, Any]] = {}
    phases: list[dict[str, Any]] = []

    for batch in _dependency_batches(gates):
        batch_results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futures = {
                pool.submit(
                    _run_gate,
                    gate,
                    run_id=run_id,
                    gw=gw,
                    authorize_live=authorize_live,
                    artifact_dir=artifact_dir,
                    prior={**results, **batch_results},
                    python=python,
                    npm=npm,
                ): gate["id"]
                for gate in batch
            }
            for fut in as_completed(futures):
                batch_results[futures[fut]] = fut.result()
        results.update(batch_results)
        phases.append({
            "batch": [g["id"] for g in batch],
            "gates": [batch_results[g["id"]] for g in batch],
        })

    offline_rows = [r for r in results.values() if r.get("mode") == "offline"]
    live_rows = [r for r in results.values() if r.get("mode") == "live"]

    blocked_reasons = sorted(
        {
            f"{row['gate_id']}:{row.get('detail')}"
            for row in results.values()
            if row.get("status") in {BLOCKED, CONDITIONAL, FAIL}
        }
    )

    if any(r.get("status") == FAIL for r in offline_rows):
        offline_verdict = FAIL
    elif any(r.get("status") == CONDITIONAL for r in offline_rows):
        offline_verdict = CONDITIONAL
    elif offline_rows and all(r.get("status") == PASS for r in offline_rows):
        offline_verdict = PASS
    elif not offline_rows:
        offline_verdict = SKIP
    else:
        offline_verdict = CONDITIONAL

    if live_rows:
        if any(r.get("status") == PASS for r in live_rows):
            live_verdict = PASS
        elif authorize_live:
            live_verdict = BLOCKED
        else:
            live_verdict = BLOCKED
    elif offline_only:
        live_verdict = "PENDING"
    else:
        live_verdict = BLOCKED

    if offline_verdict == FAIL:
        aggregate_verdict = FAIL
    elif offline_verdict == CONDITIONAL:
        aggregate_verdict = CONDITIONAL
    elif live_verdict == PASS:
        aggregate_verdict = PASS
    elif offline_verdict == PASS and live_verdict == "PENDING":
        aggregate_verdict = CONDITIONAL
    elif offline_verdict == PASS:
        aggregate_verdict = PASS if live_verdict == PASS else CONDITIONAL
    else:
        aggregate_verdict = BLOCKED

    artifacts = sorted(
        {
            path
            for row in results.values()
            for path in (row.get("stdout_path"), row.get("stderr_path"))
            if path
        }
    )

    return {
        "schema_version": REPORT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "manifest_path": str(MANIFEST_PATH),
        "canonical_inventory": manifest.get("canonical_inventory"),
        "gateway_sha": git_sha(gw),
        "profile_sha": git_sha(REPO),
        "phases": phases,
        "gates": results,
        "offline_verdict": offline_verdict,
        "live_verdict": live_verdict,
        "aggregate_verdict": aggregate_verdict,
        "artifacts": artifacts,
        "blocked_reasons": blocked_reasons,
        "authorize_live": authorize_live,
        "offline_only": offline_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manifest-driven evaluation gates")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--authorize-live", action="store_true", help="Allow live gates (still blocked unless implemented)")
    parser.add_argument("--include-live", action="store_true", help="Evaluate live gate definitions (default offline only)")
    parser.add_argument("--gate", action="append", default=[], help="Run only these gate ids")
    args = parser.parse_args()

    run_id = args.run_id or f"gate-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    manifest = load_manifest(args.manifest)
    if args.gate:
        allowed = set(args.gate)
        manifest = {
            **manifest,
            "gates": [g for g in manifest.get("gates", []) if g["id"] in allowed],
        }

    gw = gateway_root()
    report = run_gates(
        run_id=run_id,
        manifest=manifest,
        gw=gw,
        authorize_live=args.authorize_live,
        offline_only=not args.include_live,
        max_workers=args.max_workers,
    )

    output = args.output or (REPO / "evaluation" / "runs" / f"{run_id}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "report_path": str(output),
        "offline_verdict": report["offline_verdict"],
        "live_verdict": report["live_verdict"],
        "aggregate_verdict": report["aggregate_verdict"],
        "gateway_sha": report["gateway_sha"],
        "profile_sha": report["profile_sha"],
        "blocked_reasons_count": len(report["blocked_reasons"]),
    }, indent=2))

    if report["offline_verdict"] == FAIL:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
