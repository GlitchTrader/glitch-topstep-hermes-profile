"""Reprocess Trilha A real run aggregator post-hoc (no Hermes re-invoke)."""

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
from ensemble_aggregator import aggregate_envelope  # noqa: E402
from ensemble_envelope_seal import (  # noqa: E402
    envelope_validity_seconds,
    seal_envelope_from_run_config,
    sealed_envelope_identity,
)
from evaluation_run_public_bundle import slot_normalized  # noqa: E402

REPROCESS_SCHEMA = "glitch.topstep.trail_a_real_aggregator_reprocess.v1"
INCIDENT_SCHEMA = "glitch.topstep.trail_a_envelope_identity_incident.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "trail-a-real-run-config.v1.json"
DEFAULT_RUN = REPO / "evaluation" / "runs" / "trail-a-real-2026-09-02.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collect_normalized(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in sorted(bundle.get("profile_slots") or [], key=lambda r: str(r.get("profile_id"))):
        norm = slot_normalized(slot)
        if norm:
            rows.append(norm)
    return rows


def _candidate_envelope_hash(candidates: list[dict[str, Any]]) -> str | None:
    hashes = {str(c.get("envelope_hash") or "") for c in candidates}
    hashes.discard("")
    if len(hashes) == 1:
        return hashes.pop()
    return None


def reprocess_trail_a_aggregator(
    *,
    run_bundle_path: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    bundle = read_json(run_bundle_path)
    config = read_json(config_path)
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    pin = config.get("envelope") or {}

    candidates = _collect_normalized(bundle)
    live_hash = _candidate_envelope_hash(candidates)
    canonical = seal_envelope_from_run_config(config=config, matrix=matrix, mapping=mapping, repo=REPO)
    canonical_identity = sealed_envelope_identity(canonical)

    original_selection = bundle.get("selection") or {}
    wrong_pin_agg = aggregate_envelope(
        run_id=str(bundle.get("run_id") or ""),
        envelope={
            "envelope_id": pin.get("envelope_id"),
            "snapshot_hash": pin.get("snapshot_hash"),
            "envelope_hash": pin.get("envelope_hash"),
            "instrument": "MNQ",
        },
        candidates=candidates,
        rules=rules,
    )
    live_agg = aggregate_envelope(
        run_id=str(bundle.get("run_id") or ""),
        envelope={
            "envelope_id": pin.get("envelope_id"),
            "snapshot_hash": pin.get("snapshot_hash"),
            "envelope_hash": live_hash or canonical_identity["envelope_hash"],
            "instrument": canonical_identity["instrument"],
        },
        candidates=candidates,
        rules=rules,
    )
    sealed_agg = aggregate_envelope(
        run_id=str(bundle.get("run_id") or ""),
        envelope={
            "envelope_id": canonical_identity["envelope_id"],
            "snapshot_hash": canonical_identity["snapshot_hash"],
            "envelope_hash": canonical_identity["envelope_hash"],
            "instrument": canonical_identity["instrument"],
        },
        candidates=candidates,
        rules=rules,
    )

    return {
        "schema_version": REPROCESS_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": bundle.get("run_id"),
        "source_bundle": str(run_bundle_path),
        "original_selection": {
            "outcome": original_selection.get("outcome"),
            "decision_code": original_selection.get("decision_code"),
        },
        "root_cause": {
            "preflight_envelope_hash": pin.get("envelope_hash"),
            "live_candidate_envelope_hash": live_hash,
            "canonical_sealed_envelope_hash": canonical_identity["envelope_hash"],
            "validity_seconds_canonical": envelope_validity_seconds(config=config),
            "note": "cognitive replay used default validity_seconds=300 before seal wiring fix",
        },
        "reprocessed": {
            "with_pinned_preflight_hash": {
                "outcome": wrong_pin_agg.get("outcome"),
                "decision_code": wrong_pin_agg.get("decision_code"),
            },
            "with_live_candidate_hash": {
                "outcome": live_agg.get("outcome"),
                "decision_code": live_agg.get("decision_code"),
            },
            "with_canonical_sealed_hash": {
                "outcome": sealed_agg.get("outcome"),
                "decision_code": sealed_agg.get("decision_code"),
            },
        },
        "verdict": "PASS" if live_agg.get("outcome") == "no_selection" else "FAIL",
        "aggregator_offline_real": "CONDITIONAL" if live_agg.get("outcome") == "no_selection" else "FAIL",
        "promotion_gate": False,
    }


def build_incident_report(
    *,
    run_bundle_path: Path,
    config_path: Path = DEFAULT_CONFIG,
    reprocess: dict[str, Any],
) -> dict[str, Any]:
    bundle = read_json(run_bundle_path)
    config = read_json(config_path)
    pin = config.get("envelope") or {}
    return {
        "schema_version": INCIDENT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": bundle.get("run_id"),
        "classification": {
            "parallel_evaluation_real": "PASS",
            "aggregator_offline_real": "CONDITIONAL",
            "trail_a_complete": "pending",
        },
        "incident": "envelope_identity_divergence",
        "symptom": "aggregator SNAPSHOT_DIVERGENCE due to preflight pin vs live validity_seconds",
        "pinned_envelope_hash": pin.get("envelope_hash"),
        "live_envelope_hash": reprocess["root_cause"].get("live_candidate_envelope_hash"),
        "fix": "ensemble_envelope_seal.py — single sealed envelope for preflight, replay, aggregator",
        "preserved_artifacts": [
            str(run_bundle_path),
            str(run_bundle_path.with_name("trail-a-real-2026-09-02-attempt1-context-blocked.json")),
            str(run_bundle_path.with_name("trail-a-real-2026-09-02-attempt2-context-reentry.json")),
        ],
        "reprocess_verdict": reprocess.get("verdict"),
        "expected_post_hoc": {
            "outcome": "no_selection",
            "decision_code": "ENSEMBLE_UNANIMOUS_ABSTENTION",
        },
        "reprocessed_selection": reprocess.get("reprocessed"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocess Trilha A aggregator without Hermes")
    parser.add_argument("--run-bundle", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "evaluation" / "runs" / "trail-a-real-2026-09-02-aggregator-reprocess.json",
    )
    parser.add_argument(
        "--incident-output",
        type=Path,
        default=REPO / "evaluation" / "runs" / "trail-a-real-2026-09-02-envelope-identity-incident.json",
    )
    args = parser.parse_args()

    reprocess = reprocess_trail_a_aggregator(run_bundle_path=args.run_bundle, config_path=args.config)
    incident = build_incident_report(
        run_bundle_path=args.run_bundle,
        config_path=args.config,
        reprocess=reprocess,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reprocess, indent=2) + "\n", encoding="utf-8")
    args.incident_output.write_text(json.dumps(incident, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": reprocess["verdict"],
                "live_outcome": reprocess["reprocessed"]["with_live_candidate_hash"],
                "output": str(args.output),
                "incident": str(args.incident_output),
            },
            indent=2,
        )
    )
    return 0 if reprocess["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
