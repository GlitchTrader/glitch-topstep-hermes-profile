"""Phase 7 validation sequence — package, shadow offline, replay audit, isolation, metrics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

VALIDATION_SCHEMA = "glitch.topstep.shadow_phase7_validation.v1"
DEFAULT_RUN_ID = "shadow-phase7-validation-2026-09-02"
TRAIL_A_BUNDLE = REPO / "evaluation" / "runs" / "trail-a-multi-envelope-2026-09-02.json"
MILESTONE_SHADOW = REPO / "evaluation" / "runs" / "eval-milestone-six-profiles-2026-09-02-shadow-offline.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_phase7_validation(*, run_id: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    runs_dir = REPO / "evaluation" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    package_mod = _load("build_package", "build-evaluation-release-package.py")
    package_path = REPO / "evaluation" / "release" / f"{run_id}-package.json"
    package = package_mod.build_release_package(package_id=f"{run_id}-package")
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    steps.append({"step": "release_package", "ok": package.get("valid"), "artifact": str(package_path)})

    shadow_live = _load("shadow_observe_live", "shadow-observe-live.py")
    offline_path = runs_dir / f"{run_id}-shadow-offline-prep.json"
    offline = shadow_live.run_shadow_offline_prep(run_id=f"{run_id}-offline")
    offline_path.write_text(json.dumps(offline, indent=2) + "\n", encoding="utf-8")
    obs = offline.get("observation") or {}
    steps.append(
        {
            "step": "shadow_observer_offline",
            "ok": obs.get("intents_sent") == 0 and obs.get("writes_operacionais") == 0,
            "artifact": str(offline_path),
        }
    )

    replay_ok = TRAIL_A_BUNDLE.is_file()
    replay_detail = "trail_a_bundle_preserved_read_only"
    if replay_ok:
        bundle = json.loads(TRAIL_A_BUNDLE.read_text(encoding="utf-8"))
        replay_ok = bundle.get("status") == "completed" and bundle.get("production_paths_untouched") is True
        replay_detail = {
            "bundle": str(TRAIL_A_BUNDLE),
            "frame_count": len(bundle.get("frame_results") or []),
            "session_cost_usd": bundle.get("session_cost_usd"),
        }
    steps.append({"step": "replay_preserved_events", "ok": replay_ok, "detail": replay_detail})

    iso_mod = _load("audit_isolation", "audit-shadow-isolation.py")
    iso_report = iso_mod.audit_shadow_session(offline)
    iso_path = runs_dir / f"{run_id}-isolation-audit.json"
    iso_path.write_text(json.dumps(iso_report, indent=2) + "\n", encoding="utf-8")
    steps.append({"step": "isolation_audit", "ok": iso_report.get("valid"), "artifact": str(iso_path)})

    metrics_mod = _load("report_metrics", "report-shadow-metrics.py")
    metric_sources = [offline_path]
    if MILESTONE_SHADOW.is_file():
        metric_sources.append(MILESTONE_SHADOW)
    metrics = metrics_mod.build_shadow_metrics_report(observation_paths=metric_sources)
    metrics_path = runs_dir / f"{run_id}-shadow-metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    steps.append(
        {
            "step": "shadow_metrics",
            "ok": metrics.get("operational_writes_total") == 0,
            "artifact": str(metrics_path),
        }
    )

    preflight_mod = _load("shadow_preflight", "shadow-preflight.py")
    preflight = preflight_mod.shadow_preflight(run_id=run_id, package_path=package_path)
    preflight_path = runs_dir / f"{run_id}-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    steps.append(
        {
            "step": "shadow_preflight_prep",
            "ok": preflight.get("promotion_use_allowed") is False
            and preflight.get("production_parallelism") == "blocked",
            "artifact": str(preflight_path),
            "status": preflight.get("status"),
        }
    )

    blocked = shadow_live.run_shadow_session(run_id=run_id, authorize=False)
    steps.append(
        {
            "step": "live_execution_blocked_without_authorization",
            "ok": blocked.get("status") == "blocked",
            "reason": blocked.get("reason"),
        }
    )

    all_ok = all(s.get("ok") for s in steps)
    return {
        "schema_version": VALIDATION_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "verdict": "PASS" if all_ok else "FAIL",
        "shadow_live_execution_authorized": False,
        "steps": steps,
        "promotion_use_allowed": False,
        "production_parallelism": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 7 shadow validation sequence")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()

    if args.run_tests:
        subprocess.check_call(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_shadow_phase7.py", "-v"],
            cwd=REPO,
        )

    report = run_phase7_validation(run_id=args.run_id)
    out = args.output or (REPO / "evaluation" / "runs" / f"{args.run_id}.json")
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(out)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
