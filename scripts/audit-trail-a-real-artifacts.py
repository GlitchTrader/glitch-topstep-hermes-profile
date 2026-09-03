"""Post-run artifact audit for Trilha A real Hermes execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import read_json  # noqa: E402
from ensemble_aggregator import aggregate_envelope  # noqa: E402
from evaluation_lease import evaluation_lease_active  # noqa: E402
from evaluation_owner import production_state_root  # noqa: E402
from evaluation_run_public_bundle import slot_normalized, slot_replay_fields  # noqa: E402

AUDIT_SCHEMA = "glitch.topstep.trail_a_real_artifact_audit.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "trail-a-real-run-config.v1.json"


def audit_trail_a_real_run(
    *,
    run_bundle_path: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    bundle = read_json(run_bundle_path)
    config = read_json(config_path)
    pin = config.get("envelope") or {}
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    issues: list[str] = []

    if bundle.get("status") != "completed":
        issues.append(f"run_status:{bundle.get('status')}")

    if bundle.get("sealed_snapshot_hash") != pin.get("snapshot_hash"):
        issues.append("snapshot_hash_divergence")
    if bundle.get("envelope_hash") != pin.get("envelope_hash"):
        issues.append("envelope_hash_divergence")

    if not bundle.get("production_paths_untouched"):
        issues.append("production_paths_not_confirmed")

    prod_state = production_state_root()
    if evaluation_lease_active(prod_state):
        issues.append("evaluation_lease_still_active")

    profile_checks: list[dict[str, Any]] = []
    normalized_for_agg: list[dict[str, Any]] = []
    for slot in bundle.get("profile_slots") or []:
        replay = slot_replay_fields(slot)
        status = replay.get("status") or slot.get("status")
        if status != "completed":
            issues.append(f"profile_incomplete:{slot.get('profile_id')}")
        slot_snapshot = slot.get("snapshot_hash") or (slot.get("artifact") or {}).get("snapshot_hash")
        if slot_snapshot and slot_snapshot != pin.get("snapshot_hash"):
            issues.append(f"snapshot_divergence:{slot.get('profile_id')}")
        norm = slot_normalized(slot)
        if not norm:
            issues.append(f"missing_normalized:{slot.get('profile_id')}")
        else:
            normalized_for_agg.append(norm)
        profile_checks.append(
            {
                "profile_id": slot.get("profile_id"),
                "invocation_id": replay.get("invocation_id"),
                "has_raw": replay.get("raw_profile_output") is not None,
                "has_normalized": norm is not None,
                "latency_ms": replay.get("latency_ms"),
                "cost_usd": replay.get("cost_usd"),
                "model": replay.get("model"),
                "provider": replay.get("provider"),
                "prompt_version": replay.get("prompt_version"),
            }
        )

    selection = bundle.get("selection") or {}
    if not selection:
        envelope = {
            "envelope_id": pin.get("envelope_id"),
            "snapshot_hash": pin.get("snapshot_hash"),
            "envelope_hash": pin.get("envelope_hash"),
            "instrument": "MNQ",
        }
        selection = aggregate_envelope(
            run_id=str(bundle.get("run_id") or ""),
            envelope=envelope,
            candidates=normalized_for_agg,
            rules=rules,
        )

    return {
        "schema_version": AUDIT_SCHEMA,
        "run_id": bundle.get("run_id"),
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "profile_checks": profile_checks,
        "aggregator_selection": {
            "outcome": selection.get("outcome"),
            "decision_code": selection.get("decision_code"),
            "selected_profile_id": selection.get("selected_profile_id"),
        },
        "session_cost_usd": bundle.get("session_cost_usd"),
        "lease_released": not evaluation_lease_active(prod_state),
        "promotion_gate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Trilha A real run artifacts")
    parser.add_argument("run_bundle", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    report = audit_trail_a_real_run(run_bundle_path=args.run_bundle, config_path=args.config)
    output = args.output or args.run_bundle.with_name(args.run_bundle.stem + "-artifact-audit.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
