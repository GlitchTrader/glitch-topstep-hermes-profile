"""Single-shot shadow read-only attempt — one health check, no polling.

Default: preflight + capture only (shadow blocked). Pass --authorize to run live cycle when ready=true.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
RUNS = REPO / "evaluation" / "runs"
sys.path.insert(0, str(SCRIPTS))

from common import read_json, utc_now  # noqa: E402
from evaluation_owner import production_state_root  # noqa: E402
from shadow_gateway_readonly import ShadowGatewayError, fetch_gateway_health_readonly  # noqa: E402

REPORT_SCHEMA = "glitch.topstep.shadow_single_attempt.v1"
CAPTURE_MODE = "delivery_complete"
MODE = "gateway_read_only_live"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _health_blockers(health: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = str(health.get("status") or "").lower()
    if status and status != "ok":
        blockers.append(f"gateway_status_{status}")
    mode = str(health.get("gateway_mode") or health.get("mode") or "").lower()
    if "degraded" in mode:
        blockers.append("gateway_degraded")
    recovery = health.get("recovery")
    if isinstance(recovery, dict):
        phase = str(recovery.get("phase") or "").lower()
        if phase in {"failed", "blocked", "running"}:
            blockers.append(f"recovery_{phase}")
    return blockers


def run_single_attempt(
    *,
    run_id: str,
    authorize: bool = False,
    state_root: Path | None = None,
) -> dict[str, Any]:
    capture_mod = _load("capture_coherent_evaluation_bundle", SCRIPTS / "capture_coherent_evaluation_bundle.py")
    preflight_mod = _load("shadow_preflight", SCRIPTS / "shadow-preflight.py")
    observe_mod = _load("shadow_observe_live", SCRIPTS / "shadow-observe-live.py")
    isolation_mod = _load("audit_shadow_isolation", SCRIPTS / "audit-shadow-isolation.py")
    metrics_mod = _load("report_shadow_metrics", SCRIPTS / "report-shadow-metrics.py")

    root = state_root or production_state_root()
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "authorize_requested": authorize,
        "shadow_executed": False,
        "shadow_pass": False,
    }

    try:
        health = fetch_gateway_health_readonly()
    except ShadowGatewayError as exc:
        report["stop_reason"] = "gateway_unreachable"
        report["error"] = str(exc)
        return report

    report["health"] = health
    health_blockers = _health_blockers(health)
    if health_blockers:
        report["stop_reason"] = "health_blocked"
        report["blocking_reasons"] = health_blockers
        return report

    bundle = capture_mod.capture_coherent_evaluation_bundle(
        state_root=root,
        capture_mode=CAPTURE_MODE,
        health=health,
    )
    report["coherent_bundle"] = {
        "packet_id": bundle.get("packet_id"),
        "ready": bundle.get("ready"),
        "not_ready_reason": bundle.get("not_ready_reason"),
        "snapshot_alignment": (bundle.get("identity") or {}).get("snapshot_alignment"),
    }

    preflight = preflight_mod.shadow_preflight(
        run_id=run_id,
        coherent_bundle=bundle,
        capture_mode=CAPTURE_MODE,
        gateway_health=health,
        state_root=root,
    )
    report["preflight"] = {
        "ready": preflight.get("ready"),
        "status": preflight.get("status"),
        "blocking_reasons": preflight.get("blocking_reasons"),
    }

    if not preflight.get("ready"):
        report["stop_reason"] = "preflight_not_ready"
        return report

    if not authorize:
        report["stop_reason"] = "authorize_not_passed"
        report["shadow_blocked_by_default"] = True
        return report

    session = observe_mod.run_shadow_session(
        run_id=run_id,
        mode=MODE,
        authorize=True,
        coherent_bundle=bundle,
        capture_mode=CAPTURE_MODE,
        gateway_health=health,
        state_root=root,
    )
    report["shadow_executed"] = True
    report["session_status"] = session.get("status")
    report["intents_sent"] = session.get("intents_sent", 0)
    report["orders_sent"] = session.get("orders_sent", 0)
    report["writes_operacionais"] = session.get("writes_operacionais", 0)

    isolation = isolation_mod.audit_shadow_session(session)
    report["isolation_audit"] = isolation
    obs_path = RUNS / f"{run_id}-observation.json"
    if isinstance(session.get("observation"), dict):
        obs_path.write_text(json.dumps(session["observation"], indent=2) + "\n", encoding="utf-8")
        metrics = metrics_mod.build_shadow_metrics_report(observation_paths=[obs_path])
        report["metrics"] = metrics

    report["shadow_pass"] = (
        session.get("status") == "completed"
        and report["intents_sent"] == 0
        and report["orders_sent"] == 0
        and report["writes_operacionais"] == 0
        and isolation.get("valid") is True
    )
    if not report["shadow_pass"]:
        report["stop_reason"] = "shadow_session_incomplete_or_audit_failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="One-shot shadow read-only validation (no polling)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Execute gateway_read_only_live when preflight ready=true (default: blocked)",
    )
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_single_attempt(
        run_id=args.run_id,
        authorize=args.authorize,
        state_root=args.state_root,
    )
    text = json.dumps(result, indent=2) + "\n"
    out = args.output or (RUNS / f"shadow-single-attempt-{args.run_id}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text, end="")
    if result.get("shadow_pass"):
        return 0
    if result.get("stop_reason") == "authorize_not_passed" and result.get("preflight", {}).get("ready"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
