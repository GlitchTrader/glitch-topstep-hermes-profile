"""Preflight checks before cognitive replay — production lane + evaluation lease."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import read_json
from evaluation_lease import evaluation_lease_active, read_evaluation_lease
from evaluation_owner import production_lane_active, production_profile_root, production_state_root

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent


def _latest_lease_smoke_report() -> tuple[Path | None, dict[str, Any] | None]:
    runs_dir = REPO / "evaluation" / "runs"
    if not runs_dir.is_dir():
        return None, None
    candidates = sorted(runs_dir.glob("lease-smoke*.json"), reverse=True)
    for path in candidates:
        if path.name.endswith("-fault.json"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict):
            return path, doc
    return None, None


def preflight_evaluation_replay(
    *,
    run_id: str,
    scenarios_path: Path | None = None,
    production_state: Path | None = None,
) -> dict[str, Any]:
    prod_state = production_state or production_state_root()
    checks: list[dict[str, Any]] = []

    lane_active = production_lane_active(production_state=prod_state)

    lease = read_evaluation_lease(prod_state)
    lease_active = evaluation_lease_active(prod_state)
    lease_ok = not lease_active or str((lease or {}).get("run_id") or "") == run_id
    checks.append(
        {
            "id": "evaluation_lease_available",
            "ok": lease_ok,
            "detail": "no foreign evaluation lease on production state",
            "blocking_run_id": None if lease_ok else (lease or {}).get("run_id"),
        }
    )

    scenarios_ok = True
    if scenarios_path is not None:
        scenarios_ok = scenarios_path.is_file()
        doc = read_json(scenarios_path) if scenarios_ok else {}
        scenarios_ok = scenarios_ok and bool(doc.get("scenarios"))
    checks.append(
        {
            "id": "scenarios_manifest_present",
            "ok": scenarios_ok,
            "detail": str(scenarios_path) if scenarios_path else "not_required",
        }
    )

    prod_root = production_profile_root()
    sync_path = prod_root / "state" / "lease-coordination-sync.json"
    sync_ok = False
    sync_detail = "lease-coordination-sync.json missing"
    if sync_path.is_file():
        try:
            sync_doc = json.loads(sync_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            sync_doc = {}
        sync_ok = bool(sync_doc.get("all_matched"))
        synced_utc = sync_doc.get("synced_utc")
        sync_detail = (
            f"all_matched={sync_doc.get('all_matched')} synced_utc={synced_utc}"
            if isinstance(sync_doc, dict)
            else "invalid sync manifest"
        )
    checks.append(
        {
            "id": "lease_scripts_synced",
            "ok": sync_ok,
            "detail": sync_detail,
            "manifest_path": str(sync_path),
        }
    )

    smoke_path, smoke_doc = _latest_lease_smoke_report()
    smoke_ok = False
    if isinstance(smoke_doc, dict):
        smoke_ok = bool(smoke_doc.get("ok"))
        if not smoke_ok:
            smoke_mode = (smoke_doc.get("modes") or {}).get("smoke")
            smoke_ok = bool(isinstance(smoke_mode, dict) and smoke_mode.get("ok"))
    smoke_detail = (
        f"lease smoke ok={smoke_ok} path={smoke_path.name}"
        if smoke_path
        else "no lease-smoke report in evaluation/runs/"
    )
    checks.append(
        {
            "id": "lease_smoke_passed",
            "ok": smoke_ok,
            "detail": smoke_detail,
            "report_path": str(smoke_path) if smoke_path else None,
            "required": True,
        }
    )

    checks.append(
        {
            "id": "coordination_contract",
            "ok": sync_ok and smoke_ok,
            "detail": "evaluation_lease.py + cron defer + sync manifest + lease smoke",
        }
    )

    coordination_ok = sync_ok and smoke_ok
    checks.insert(
        0,
        {
            "id": "production_lane_inactive",
            "ok": (not lane_active) or coordination_ok,
            "detail": (
                "lane idle, or LIVE_VALIDATED lease defers cron while replay holds lease"
            ),
            "lane_active": lane_active,
            "coordination_live_validated": coordination_ok,
        },
    )

    ok = all(row.get("ok") for row in checks)
    return {
        "schema_version": "glitch.topstep.preflight_evaluation_replay.v1",
        "run_id": run_id,
        "ok": ok,
        "checks": checks,
        "production_state": str(prod_state),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight cognitive replay coordination")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenarios", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    scenarios = None
    if args.scenarios:
        scenarios = args.scenarios if args.scenarios.is_absolute() else REPO / args.scenarios

    report = preflight_evaluation_replay(run_id=args.run_id, scenarios_path=scenarios)
    out = args.output
    if out:
        path = out if out.is_absolute() else REPO / out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
