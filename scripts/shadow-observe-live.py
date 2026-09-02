"""Phase 7 shadow live observer — evaluation lane, observational only (blocked until --authorize)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import read_json, utc_now  # noqa: E402
from ensemble_aggregator import aggregate_envelope  # noqa: E402
from ensemble_capability import capacity_gate  # noqa: E402
from ensemble_envelope_seal import (  # noqa: E402
    envelope_validity_seconds,
    seal_evaluation_envelope_from_frame,
    sealed_envelope_identity,
)
from ensemble_parallel_runner import cleanup_work_dirs, run_profiles_parallel  # noqa: E402
from evaluation_cognitive_replay import (  # noqa: E402
    assert_operational_artifacts_unchanged,
    operational_artifact_snapshot,
)
from evaluation_owner import production_state_root  # noqa: E402
from shadow_observation import OBSERVATION_LIVE_SCHEMA, build_shadow_observation  # noqa: E402

DEFAULT_CONFIG = REPO / "evaluation" / "shadow-live-run-config.v1.json"
DEFAULT_FRAME = REPO / "tests" / "fixtures" / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json"
SESSION_SCHEMA = "glitch.topstep.shadow_live_session.v1"


def _load_seq():
    spec = importlib.util.spec_from_file_location("run_ensemble_evaluation", SCRIPTS / "run-ensemble-evaluation.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_preflight():
    spec = importlib.util.spec_from_file_location("shadow_preflight", SCRIPTS / "shadow-preflight.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def observe_shadow_six_profiles(
    *,
    run_id: str,
    envelope: dict[str, Any],
    registry: dict[str, Any],
    matrix: dict[str, Any],
    rules: dict[str, Any],
    config: dict[str, Any],
    fixtures_dir: Path,
    shadow_live: bool,
    prod_before: dict[str, Any] | None = None,
    prod_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seq = _load_seq()
    baseline_id = str(registry.get("baseline_policy") or "baseline-current")
    profiles = [p for p in registry.get("profiles") or [] if p.get("enabled", True)]
    budget = config.get("budget") or {}
    frame_id = str(envelope.get("frame_id") or envelope.get("envelope_id") or "shadow")

    def loader(profile_id: str, fid: str) -> dict[str, Any] | None:
        path = fixtures_dir / profile_id / f"{fid}.json"
        return read_json(path) if path.is_file() else None

    def builder(**kwargs: Any) -> dict[str, Any]:
        return seq.build_normalized_candidate(**kwargs)

    gates = {str(p["profile_id"]): capacity_gate(envelope, str(p["profile_id"]), matrix) for p in profiles}
    slot_results = run_profiles_parallel(
        profiles=profiles,
        frame_id=frame_id,
        run_id=run_id,
        envelope=envelope,
        gates_by_profile=gates,
        loader=loader,
        builder=builder,
        max_parallel_slots=int(budget.get("max_parallel_slots") or 2),
        max_cost_usd=float(budget.get("max_cost_usd_per_session") or 2.5),
        per_profile_timeout_ms=int(budget.get("per_profile_timeout_ms") or 35000),
        total_timeout_ms=int(budget.get("total_timeout_ms") or 120000),
    )

    candidates: list[dict[str, Any]] = []
    profile_decisions: list[dict[str, Any]] = []
    isolation_audit: list[dict[str, Any]] = []
    total_cost = 0.0
    total_latency = 0

    for slot in slot_results:
        total_cost += slot.estimated_cost_usd
        total_latency += slot.latency_ms
        work_dir = Path(slot.work_dir)
        isolation_audit.append(
            {
                "profile_id": slot.profile_id,
                "invocation_id": slot.invocation_id,
                "work_dir": str(work_dir),
                "hermes_home_isolated": (work_dir / "HERMES_HOME_ISOLATED").is_file(),
                "profile_outside_evaluation_home": False,
                "error": slot.error,
                "cancelled": slot.cancelled,
            }
        )
        if slot.normalized is None:
            profile_decisions.append(
                {
                    "profile_id": slot.profile_id,
                    "invocation_id": slot.invocation_id,
                    "state": "error",
                    "direction": None,
                    "latency_ms": slot.latency_ms,
                    "cost_usd": slot.estimated_cost_usd,
                    "is_baseline": slot.profile_id == baseline_id,
                    "error": slot.error or "profile_unavailable",
                }
            )
            continue
        norm = slot.normalized
        candidates.append(norm)
        profile_decisions.append(
            {
                "profile_id": slot.profile_id,
                "invocation_id": norm.get("invocation_id"),
                "state": norm.get("state"),
                "direction": norm.get("direction"),
                "comparability": norm.get("comparability"),
                "capacity_gate_reason": norm.get("capacity_gate_reason"),
                "completeness_used": norm.get("completeness_used"),
                "latency_ms": slot.latency_ms,
                "cost_usd": slot.estimated_cost_usd,
                "is_baseline": slot.profile_id == baseline_id,
            }
        )

    selection = aggregate_envelope(
        run_id=run_id,
        envelope={
            "envelope_id": envelope.get("envelope_id"),
            "snapshot_hash": envelope.get("snapshot_hash"),
            "envelope_hash": envelope.get("envelope_hash"),
            "instrument": envelope.get("instrument"),
            "contract": envelope.get("contract") or {"tick_size": 0.25},
            "packet": envelope.get("packet") or {},
        },
        candidates=candidates,
        objections=[],
        rules=rules,
    )

    operational_writes = False
    if prod_before is not None and prod_after is not None:
        try:
            assert_operational_artifacts_unchanged(prod_before, prod_after)
        except PermissionError:
            operational_writes = True

    cleanup_work_dirs(run_id)
    return build_shadow_observation(
        run_id=run_id,
        envelope=envelope,
        profile_decisions=profile_decisions,
        candidates=candidates,
        selection=selection,
        baseline_id=baseline_id,
        cost_usd=total_cost,
        latency_ms_total=total_latency,
        shadow_live=shadow_live,
        schema_version=OBSERVATION_LIVE_SCHEMA,
        isolation_audit=isolation_audit,
        operational_writes_detected=operational_writes,
        gateway_touched=shadow_live,
        profile_source="fixtures" if not shadow_live else "hermes",
    )


def run_shadow_session(
    *,
    run_id: str,
    config_path: Path = DEFAULT_CONFIG,
    frame_path: Path = DEFAULT_FRAME,
    fixtures_dir: Path | None = None,
    authorize: bool = False,
    gateway_health: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preflight_mod = _load_preflight()
    preflight = preflight_mod.shadow_preflight(
        run_id=run_id,
        config_path=config_path,
        gateway_health=gateway_health,
        packet=packet,
    )

    if not authorize:
        return {
            "schema_version": SESSION_SCHEMA,
            "generated_utc": utc_now(),
            "run_id": run_id,
            "status": "blocked",
            "reason": "human_authorization_required",
            "preflight": preflight,
            "shadow_live": False,
            "intents_sent": 0,
            "orders_sent": 0,
            "writes_operacionais": 0,
        }

    if not preflight.get("ready"):
        return {
            "schema_version": SESSION_SCHEMA,
            "generated_utc": utc_now(),
            "run_id": run_id,
            "status": preflight.get("status") or "shadow_not_ready",
            "preflight": preflight,
            "shadow_live": False,
            "intents_sent": 0,
            "orders_sent": 0,
            "writes_operacionais": 0,
        }

    config = read_json(config_path)
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    fixtures = fixtures_dir or (REPO / "tests" / "fixtures" / "ensemble_candidates")

    frame = read_json(frame_path)
    frame_id = str(frame.get("minute_id") or frame_path.stem)
    sealed = seal_evaluation_envelope_from_frame(
        frame=frame,
        source_catalog=matrix["source_catalog"],
        mapping=mapping,
        validity_seconds=envelope_validity_seconds(budget=config.get("budget")),
        frame_path=str(frame_path.parent),
    )
    identity = sealed_envelope_identity(sealed)
    sealed["envelope_hash"] = identity["envelope_hash"]
    sealed["frame_id"] = frame_id

    prod_state = production_state_root()
    prod_before = operational_artifact_snapshot(prod_state)
    observation = observe_shadow_six_profiles(
        run_id=run_id,
        envelope=sealed,
        registry=registry,
        matrix=matrix,
        rules=rules,
        config=config,
        fixtures_dir=fixtures,
        shadow_live=True,
        prod_before=prod_before,
        prod_after=operational_artifact_snapshot(prod_state),
    )

    stop_reasons: list[str] = []
    if observation.get("writes_operacionais"):
        stop_reasons.append("write_operacional")
    if observation.get("isolation_failures"):
        stop_reasons.append("isolation_failure")
    if observation.get("cost_usd", 0) <= 0 and config.get("require_known_cost"):
        stop_reasons.append("custo_desconhecido")

    status = "completed" if not stop_reasons else "stopped"
    return {
        "schema_version": SESSION_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "status": status,
        "stop_reasons": stop_reasons,
        "preflight": preflight,
        "observation": observation,
        "shadow_live": True,
        "intents_sent": 0,
        "orders_sent": 0,
        "writes_operacionais": observation.get("writes_operacionais", 0),
        "production_parallelism": "blocked",
        "promotion_use_allowed": False,
    }


def run_shadow_offline_prep(
    *,
    run_id: str,
    frame_path: Path = DEFAULT_FRAME,
    fixtures_dir: Path | None = None,
) -> dict[str, Any]:
    """Offline prep path — real preserved snapshot, fixture profiles, zero gateway."""
    config = read_json(DEFAULT_CONFIG)
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    fixtures = fixtures_dir or (REPO / "tests" / "fixtures" / "ensemble_candidates")
    frame = read_json(frame_path)
    frame_id = str(frame.get("minute_id") or frame_path.stem)
    sealed = seal_evaluation_envelope_from_frame(
        frame=frame,
        source_catalog=matrix["source_catalog"],
        mapping=mapping,
        validity_seconds=envelope_validity_seconds(budget=config.get("budget")),
        frame_path=str(frame_path.parent),
    )
    identity = sealed_envelope_identity(sealed)
    sealed["envelope_hash"] = identity["envelope_hash"]
    sealed["frame_id"] = frame_id

    observation = observe_shadow_six_profiles(
        run_id=run_id,
        envelope=sealed,
        registry=registry,
        matrix=matrix,
        rules=rules,
        config=config,
        fixtures_dir=fixtures,
        shadow_live=False,
    )
    return {
        "schema_version": SESSION_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "status": "offline_prep_complete",
        "observation": observation,
        "shadow_live": False,
        "intents_sent": 0,
        "orders_sent": 0,
        "writes_operacionais": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 shadow observer (blocked until --authorize)")
    parser.add_argument("--run-id", default=f"shadow-live-prep-{uuid.uuid4()}")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--frame", type=Path, default=DEFAULT_FRAME)
    parser.add_argument("--fixtures-dir", type=Path)
    parser.add_argument("--gateway-health", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--offline-prep", action="store_true", help="Offline prep only (default without --authorize)")
    parser.add_argument("--authorize", action="store_true", help="Human authorization — still requires preflight PASS")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    health = read_json(args.gateway_health) if args.gateway_health and args.gateway_health.is_file() else None
    packet_doc = read_json(args.packet) if args.packet and args.packet.is_file() else None
    packet = packet_doc.get("packet") if isinstance(packet_doc, dict) and isinstance(packet_doc.get("packet"), dict) else packet_doc

    if args.offline_prep or not args.authorize:
        result = run_shadow_offline_prep(
            run_id=args.run_id,
            frame_path=args.frame,
            fixtures_dir=args.fixtures_dir,
        )
        if not args.offline_prep and not args.authorize:
            preflight = _load_preflight().shadow_preflight(
                run_id=args.run_id,
                config_path=args.config,
                gateway_health=health,
                packet=packet,
            )
            result["preflight"] = preflight
            result["status"] = "blocked"
            result["reason"] = "human_authorization_required"
    else:
        result = run_shadow_session(
            run_id=args.run_id,
            config_path=args.config,
            frame_path=args.frame,
            fixtures_dir=args.fixtures_dir,
            authorize=True,
            gateway_health=health,
            packet=packet,
        )

    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result.get("status") in {"offline_prep_complete", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
