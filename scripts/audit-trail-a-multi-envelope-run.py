"""Post-run audit for Trilha A multi-envelope Hermes execution."""

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

from common import read_json  # noqa: E402
from evaluation_lease import evaluation_lease_active  # noqa: E402
from evaluation_cognitive_replay import operational_artifact_snapshot  # noqa: E402
from evaluation_owner import production_state_root  # noqa: E402

AUDIT_SCHEMA = "glitch.topstep.trail_a_multi_envelope_post_audit.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "trail-a-multi-envelope-run-config.v1.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def audit_multi_envelope_run(
    *,
    run_bundle_path: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    bundle = read_json(run_bundle_path)
    config = read_json(config_path)
    pins = {str(p.get("scenario_id") or ""): p for p in config.get("envelopes") or []}
    issues: list[str] = []
    envelope_audits: list[dict[str, Any]] = []

    if bundle.get("status") != "completed":
        issues.append(f"run_status:{bundle.get('status')}")

    if not bundle.get("production_paths_untouched"):
        issues.append("production_paths_not_confirmed")

    prod_state = production_state_root()
    prod_before_after_ok = operational_artifact_snapshot(prod_state) is not None
    if evaluation_lease_active(prod_state):
        issues.append("evaluation_lease_still_active")

    all_invocation_ids: list[str] = []
    for frame in bundle.get("frame_results") or []:
        scenario_id = str(frame.get("scenario_id") or "")
        pin = pins.get(scenario_id) or {}
        frame_issues: list[str] = []
        sealed_snap = str(frame.get("sealed_snapshot_hash") or "")
        sealed_env = str(frame.get("sealed_envelope_hash") or "")
        if sealed_snap != str(pin.get("snapshot_hash") or ""):
            frame_issues.append("snapshot_hash_mismatch")
        if sealed_env != str(pin.get("envelope_hash") or ""):
            frame_issues.append("envelope_hash_mismatch")
        if not frame.get("identity_ok"):
            frame_issues.append("candidate_identity_mismatch")
        if not frame.get("aggregator_ok"):
            frame_issues.append("aggregator_failed")
        selection = frame.get("selection") or {}
        if selection.get("outcome") == "classified_failure" and selection.get("decision_code") == "SNAPSHOT_DIVERGENCE":
            frame_issues.append("snapshot_divergence")

        profile_checks: list[dict[str, Any]] = []
        candidate_hashes: set[str] = set()
        for slot in frame.get("profile_slots") or []:
            art = slot.get("artifact") or {}
            if art.get("status") != "completed":
                frame_issues.append(f"profile_incomplete:{slot.get('profile_id')}")
            inv = str(art.get("invocation_id") or "")
            if inv:
                all_invocation_ids.append(inv)
            norm = art.get("normalized") or {}
            eh = str(norm.get("envelope_hash") or "")
            if eh:
                candidate_hashes.add(eh)
            if art.get("snapshot_hash") != sealed_snap:
                frame_issues.append(f"snapshot_divergence:{slot.get('profile_id')}")
            profile_checks.append(
                {
                    "profile_id": slot.get("profile_id"),
                    "invocation_id": inv,
                    "latency_ms": art.get("latency_ms"),
                    "cost_usd": art.get("cost_usd"),
                    "envelope_hash": eh,
                }
            )
        if len(candidate_hashes) != 1 or sealed_env not in candidate_hashes:
            frame_issues.append("envelope_hash_not_unanimous")
        if len(frame.get("profile_slots") or []) != 3:
            frame_issues.append("profile_count_not_three")

        issues.extend(f"{scenario_id}:{i}" for i in frame_issues)
        envelope_audits.append(
            {
                "scenario_id": scenario_id,
                "frame_id": frame.get("frame_id"),
                "sealed_snapshot_hash": sealed_snap,
                "sealed_envelope_hash": sealed_env,
                "selection": {
                    "outcome": selection.get("outcome"),
                    "decision_code": selection.get("decision_code"),
                },
                "profile_checks": profile_checks,
                "issues": frame_issues,
                "ok": not frame_issues,
            }
        )

    if len(all_invocation_ids) != len(set(all_invocation_ids)):
        issues.append("duplicate_invocation_ids")

    all_envelopes_ok = all(a["ok"] for a in envelope_audits) and len(envelope_audits) == 3
    trail_a_pass = (
        bundle.get("status") == "completed"
        and all_envelopes_ok
        and not issues
        and not evaluation_lease_active(prod_state)
    )

    return {
        "schema_version": AUDIT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": bundle.get("run_id"),
        "verdict": "PASS" if trail_a_pass else "FAIL",
        "issues": issues,
        "envelope_audits": envelope_audits,
        "session_cost_usd": bundle.get("session_cost_usd"),
        "invocation_count": len(all_invocation_ids),
        "lease_released": not evaluation_lease_active(prod_state),
        "operational_snapshot_readable": prod_before_after_ok,
        "trail_a_gate": {
            "parallel_evaluation_real": "PASS" if trail_a_pass else "FAIL",
            "aggregator_offline_real": "PASS" if all_envelopes_ok else "FAIL",
            "parallel_evaluation_acceptance": "PASS" if trail_a_pass else "FAIL",
            "trail_a_complete": "PASS" if trail_a_pass else "pending",
        },
        "promotion_gate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Trilha A multi-envelope run")
    parser.add_argument("run_bundle", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = audit_multi_envelope_run(run_bundle_path=args.run_bundle, config_path=args.config)
    output = args.output or args.run_bundle.with_name(args.run_bundle.stem + "-post-audit.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "trail_a_gate": report["trail_a_gate"], "output": str(output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
