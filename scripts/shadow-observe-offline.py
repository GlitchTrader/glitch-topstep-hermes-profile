"""Shadow-only offline observer — envelope → profiles → aggregator → baseline comparison."""

from __future__ import annotations

import argparse
import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys_path_inserted = False

OBSERVATION_SCHEMA = "glitch.topstep.shadow_observation_offline.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_seq():
    spec = importlib.util.spec_from_file_location("run_ensemble_evaluation", SCRIPTS / "run-ensemble-evaluation.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot_age_ms(envelope: dict[str, Any]) -> int | None:
    ref = str(envelope.get("reference_utc") or "")
    if not ref:
        return None
    try:
        ref_dt = datetime.fromisoformat(ref.replace("Z", "+00:00")).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, int((now - ref_dt).total_seconds() * 1000))
    except ValueError:
        return None


def observe_envelope_offline(
    *,
    envelope: dict[str, Any],
    profile_fixtures: dict[str, dict[str, Any] | None],
    registry: dict[str, Any],
    matrix: dict[str, Any],
    rules: dict[str, Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    from ensemble_aggregator import aggregate_envelope
    from ensemble_capability import capacity_gate

    seq = _load_seq()
    baseline_id = str(registry.get("baseline_policy") or "baseline-current")
    effective_run_id = run_id or f"shadow-offline-{uuid.uuid4()}"
    started = utc_now()

    profile_rows = [p for p in registry.get("profiles") or [] if p.get("enabled", True)]
    profile_decisions: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    total_latency = 0
    total_cost = 0.0

    for profile in profile_rows:
        pid = str(profile["profile_id"])
        gate = capacity_gate(envelope, pid, matrix)
        fixture = profile_fixtures.get(pid)
        latency = int((fixture or {}).get("latency_ms") or 0)
        cost = float((fixture or {}).get("cost_usd") or 0.0)
        total_latency += latency
        total_cost += cost
        norm = seq.build_normalized_candidate(
            fixture=fixture,
            run_id=effective_run_id,
            profile=profile,
            envelope=envelope,
            gate=gate,
            started_utc=started,
            finished_utc=utc_now(),
            latency_ms=latency,
        )
        candidates.append(norm)
        profile_decisions.append(
            {
                "profile_id": pid,
                "invocation_id": norm.get("invocation_id"),
                "state": norm.get("state"),
                "direction": norm.get("direction"),
                "comparability": norm.get("comparability"),
                "capacity_gate_reason": norm.get("capacity_gate_reason"),
                "completeness_used": norm.get("completeness_used"),
                "latency_ms": latency,
                "cost_usd": cost,
                "is_baseline": pid == baseline_id,
            }
        )

    envelope_for_agg = {
        "envelope_id": envelope.get("envelope_id"),
        "snapshot_hash": envelope.get("snapshot_hash"),
        "envelope_hash": envelope.get("envelope_hash"),
        "instrument": envelope.get("instrument"),
        "contract": envelope.get("contract") or {"tick_size": 0.25},
        "packet": envelope.get("packet") or {},
    }
    selection = aggregate_envelope(
        run_id=effective_run_id,
        envelope=envelope_for_agg,
        candidates=candidates,
        objections=[],
        rules=rules,
    )

    from shadow_observation import OBSERVATION_OFFLINE_SCHEMA, build_shadow_observation
    from shadow_modes import MODE_FIXTURE_OFFLINE, enrich_observation_package, mode_flags

    flags = mode_flags(MODE_FIXTURE_OFFLINE)
    observation = build_shadow_observation(
        run_id=effective_run_id,
        envelope=envelope,
        profile_decisions=profile_decisions,
        candidates=candidates,
        selection=selection,
        baseline_id=baseline_id,
        cost_usd=total_cost,
        latency_ms_total=total_latency,
        shadow_live=flags["shadow_live"],
        schema_version=OBSERVATION_OFFLINE_SCHEMA,
        gateway_touched=False,
        profile_source="fixtures",
    )
    return enrich_observation_package(
        observation,
        mode=MODE_FIXTURE_OFFLINE,
        snapshot_source="frozen_fixture",
        profile_ids=[str(p["profile_id"]) for p in profile_rows],
        aggregator_rules_version=str(rules.get("rules_version") or ""),
        registry_version=str(registry.get("registry_version") or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow-only offline envelope observer")
    parser.add_argument("--frame", type=Path, required=True, help="Frozen minute frame JSON")
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=REPO / "tests" / "fixtures" / "ensemble_candidates",
    )
    parser.add_argument("--output", type=Path, default=REPO / "evaluation" / "runs" / "shadow-observe-offline.json")
    args = parser.parse_args()

    import sys

    sys.path.insert(0, str(SCRIPTS))
    from common import read_json
    from ensemble_envelope_seal import seal_evaluation_envelope_from_frame, sealed_envelope_identity

    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    frame = read_json(args.frame)
    frame_id = str(frame.get("minute_id") or args.frame.stem)
    sealed = seal_evaluation_envelope_from_frame(
        frame=frame,
        source_catalog=matrix["source_catalog"],
        mapping=mapping,
        validity_seconds=35,
        frame_path=str(args.frame.parent),
    )
    identity = sealed_envelope_identity(sealed)
    sealed["envelope_hash"] = identity["envelope_hash"]

    fixtures: dict[str, dict[str, Any] | None] = {}
    for profile in registry.get("profiles") or []:
        pid = str(profile["profile_id"])
        path = args.fixtures_dir / pid / f"{frame_id}.json"
        fixtures[pid] = read_json(path) if path.is_file() else None

    report = observe_envelope_offline(
        envelope=sealed,
        profile_fixtures=fixtures,
        registry=registry,
        matrix=matrix,
        rules=rules,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": report["aggregator_selection"]["outcome"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
