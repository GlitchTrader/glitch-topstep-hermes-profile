"""Audit shadow observation isolation and zero-write guarantees."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from evaluation_owner import evaluation_hermes_home, production_profile_root  # noqa: E402

AUDIT_SCHEMA = "glitch.topstep.shadow_isolation_audit.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def audit_shadow_observation(observation: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if observation.get("intents_sent", 0) != 0:
        issues.append("intents_sent_nonzero")
    if observation.get("orders_sent", 0) != 0:
        issues.append("orders_sent_nonzero")
    if int(observation.get("writes_operacionais") or 0) != 0:
        issues.append("writes_operacionais_nonzero")

    eval_home = str(evaluation_hermes_home().resolve())
    prod_home = str(production_profile_root().resolve())
    if eval_home == prod_home:
        issues.append("hermes_home_not_isolated")

    for row in observation.get("isolation_audit") or []:
        if not row.get("hermes_home_isolated"):
            issues.append(f"isolation_marker_missing:{row.get('profile_id')}")
        if row.get("profile_outside_evaluation_home"):
            issues.append(f"profile_outside_evaluation_home:{row.get('profile_id')}")

    for failure in observation.get("isolation_failures") or []:
        issues.append(f"isolation_failure:{failure.get('profile_id')}")

    envelope = observation.get("envelope") or {}
    if not envelope.get("snapshot_hash") or not envelope.get("envelope_hash"):
        issues.append("envelope_identity_incomplete")

    return {
        "schema_version": AUDIT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": observation.get("run_id"),
        "valid": not issues,
        "issues": issues,
        "hermes_home_evaluation": eval_home,
        "hermes_home_production": prod_home,
        "intents_sent": observation.get("intents_sent", 0),
        "orders_sent": observation.get("orders_sent", 0),
        "writes_operacionais": observation.get("writes_operacionais", 0),
    }


def audit_shadow_session(session: dict[str, Any]) -> dict[str, Any]:
    obs = session.get("observation")
    if not isinstance(obs, dict):
        return {
            "schema_version": AUDIT_SCHEMA,
            "generated_utc": utc_now(),
            "valid": False,
            "issues": ["observation_missing"],
        }
    base = audit_shadow_observation(obs)
    if session.get("intents_sent", 0) != 0:
        base["issues"].append("session_intents_sent_nonzero")
    if session.get("writes_operacionais", 0) != 0:
        base["issues"].append("session_writes_nonzero")
    base["valid"] = not base["issues"]
    base["session_status"] = session.get("status")
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit shadow isolation and zero-write guarantees")
    parser.add_argument("--observation", type=Path, help="Single observation JSON")
    parser.add_argument("--session", type=Path, help="Shadow session JSON with observation field")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.session and args.session.is_file():
        session = json.loads(args.session.read_text(encoding="utf-8"))
        report = audit_shadow_session(session)
    elif args.observation and args.observation.is_file():
        obs = json.loads(args.observation.read_text(encoding="utf-8"))
        report = audit_shadow_observation(obs)
    else:
        print("Provide --observation or --session", file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
