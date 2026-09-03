"""Shadow observer — explicit modes; gateway read-only live requires --authorize."""

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
from shadow_gateway_readonly import ShadowGatewayError, fetch_gateway_readonly_snapshot  # noqa: E402
from shadow_modes import (  # noqa: E402
    DEFAULT_SHADOW_MODE,
    MODE_FIXTURE_OFFLINE,
    MODE_GATEWAY_READ_ONLY_LIVE,
    MODE_SNAPSHOT_FILE,
    SHADOW_MODES,
    enrich_observation_package,
    mode_flags,
)
from shadow_observation import OBSERVATION_OFFLINE_SCHEMA, build_shadow_observation  # noqa: E402

DEFAULT_CONFIG = REPO / "evaluation" / "shadow-live-run-config.v1.json"
DEFAULT_FRAME = REPO / "tests" / "fixtures" / "frozen_corpus" / "minute-frames" / "20260820T1200Z.json"
SESSION_SCHEMA = "glitch.topstep.shadow_session.v1"


def _load_coherent_capture():
    spec = importlib.util.spec_from_file_location(
        "capture_coherent_evaluation_bundle", SCRIPTS / "capture_coherent_evaluation_bundle.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    mode: str,
    prod_before: dict[str, Any] | None = None,
    prod_after: dict[str, Any] | None = None,
    gateway_touched: bool = False,
) -> dict[str, Any]:
    seq = _load_seq()
    baseline_id = str(registry.get("baseline_policy") or "baseline-current")
    profiles = [p for p in registry.get("profiles") or [] if p.get("enabled", True)]
    budget = config.get("budget") or {}
    frame_id = str(envelope.get("frame_id") or envelope.get("envelope_id") or "shadow")
    flags = mode_flags(mode)

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
    profile_source = "fixtures"
    if mode == MODE_GATEWAY_READ_ONLY_LIVE:
        profile_source = "fixtures_on_gateway_snapshot"

    observation = build_shadow_observation(
        run_id=run_id,
        envelope=envelope,
        profile_decisions=profile_decisions,
        candidates=candidates,
        selection=selection,
        baseline_id=baseline_id,
        cost_usd=total_cost,
        latency_ms_total=total_latency,
        shadow_live=flags["shadow_live"],
        schema_version=OBSERVATION_OFFLINE_SCHEMA,
        isolation_audit=isolation_audit,
        operational_writes_detected=operational_writes,
        gateway_touched=gateway_touched,
        profile_source=profile_source,
    )
    snapshot_source = {
        MODE_FIXTURE_OFFLINE: "frozen_fixture",
        MODE_SNAPSHOT_FILE: "snapshot_file",
        MODE_GATEWAY_READ_ONLY_LIVE: "gateway_readonly",
    }[mode]
    return enrich_observation_package(
        observation,
        mode=mode,
        snapshot_source=snapshot_source,
        profile_ids=[str(p["profile_id"]) for p in profiles],
        aggregator_rules_version=str(rules.get("rules_version") or ""),
        registry_version=str(registry.get("registry_version") or ""),
    )


def _seal_frame(frame_path: Path, *, config: dict[str, Any], matrix: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
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
    return sealed


def run_shadow_session(
    *,
    run_id: str,
    mode: str = DEFAULT_SHADOW_MODE,
    config_path: Path = DEFAULT_CONFIG,
    frame_path: Path | None = None,
    fixtures_dir: Path | None = None,
    authorize: bool = False,
    gateway_health: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
    http_get: Any = None,
    capture_mode: str | None = None,
    coherent_bundle: dict[str, Any] | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    if mode not in SHADOW_MODES:
        raise ValueError(f"unknown_shadow_mode:{mode}")

    capture_mod = _load_coherent_capture()
    resolved_capture_mode = capture_mode or capture_mod.CAPTURE_MODE_LIVE_GATEWAY
    if coherent_bundle is None and resolved_capture_mode == capture_mod.CAPTURE_MODE_DELIVERY_COMPLETE:
        coherent_bundle = capture_mod.capture_coherent_evaluation_bundle(
            state_root=state_root,
            capture_mode=resolved_capture_mode,
            health=gateway_health,
        )

    flags = mode_flags(mode)
    preflight_mod = _load_preflight()
    preflight = preflight_mod.shadow_preflight(
        run_id=run_id,
        config_path=config_path,
        gateway_health=gateway_health,
        packet=packet,
        coherent_bundle=coherent_bundle,
        capture_mode=resolved_capture_mode,
        state_root=state_root,
    )

    base = {
        "schema_version": SESSION_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "mode": mode,
        "capture_mode": resolved_capture_mode,
        "intents_sent": 0,
        "orders_sent": 0,
        "writes_operacionais": 0,
        "production_parallelism": "blocked",
        "promotion_use_allowed": False,
        **flags,
    }

    if mode == MODE_GATEWAY_READ_ONLY_LIVE and not authorize:
        return {
            **base,
            "status": "blocked",
            "reason": "human_authorization_required_for_gateway_read_only_live",
            "preflight": preflight,
        }

    if mode in {MODE_FIXTURE_OFFLINE, MODE_SNAPSHOT_FILE} and authorize:
        return {
            **base,
            "status": "blocked",
            "reason": "authorize_not_applicable_for_offline_modes",
            "preflight": preflight,
        }

    if mode == MODE_GATEWAY_READ_ONLY_LIVE and not preflight.get("ready"):
        return {
            **base,
            "status": preflight.get("status") or "shadow_not_ready",
            "preflight": preflight,
        }

    config = read_json(config_path)
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    fixtures = fixtures_dir or (REPO / "tests" / "fixtures" / "ensemble_candidates")

    prod_before = operational_artifact_snapshot(production_state_root())
    gateway_touched = False
    sealed: dict[str, Any]

    try:
        if (
            mode == MODE_GATEWAY_READ_ONLY_LIVE
            and resolved_capture_mode == capture_mod.CAPTURE_MODE_DELIVERY_COMPLETE
            and coherent_bundle
        ):
            envelope = coherent_bundle.get("envelope")
            if not isinstance(envelope, dict):
                return {
                    **base,
                    "status": "shadow_not_ready:coherent_bundle_incomplete",
                    "preflight": preflight,
                }
            sealed = envelope
            # delivery_complete identity from frozen profile state — not live GET /packet
        elif mode == MODE_GATEWAY_READ_ONLY_LIVE:
            snap = fetch_gateway_readonly_snapshot(
                matrix=matrix,
                mapping=mapping,
                budget=config.get("budget"),
                http_get=http_get,
            )
            sealed = snap["envelope"]
            gateway_touched = True
        else:
            path = frame_path or DEFAULT_FRAME
            if mode == MODE_SNAPSHOT_FILE and frame_path is None:
                return {**base, "status": "blocked", "reason": "snapshot_file_requires_frame"}
            sealed = _seal_frame(path, config=config, matrix=matrix, mapping=mapping)
    except ShadowGatewayError as exc:
        status = f"shadow_not_ready:{exc.code}"
        return {**base, "status": status, "preflight": preflight, "error": str(exc)}

    observation = observe_shadow_six_profiles(
        run_id=run_id,
        envelope=sealed,
        registry=registry,
        matrix=matrix,
        rules=rules,
        config=config,
        fixtures_dir=fixtures,
        mode=mode,
        prod_before=prod_before,
        prod_after=operational_artifact_snapshot(production_state_root()),
        gateway_touched=gateway_touched,
    )

    stop_reasons: list[str] = []
    if observation.get("writes_operacionais"):
        stop_reasons.append("write_operacional")
    if observation.get("isolation_failures"):
        stop_reasons.append("isolation_failure")

    status = "completed" if not stop_reasons else "stopped"
    return {
        **base,
        "status": status,
        "stop_reasons": stop_reasons,
        "preflight": preflight if mode == MODE_GATEWAY_READ_ONLY_LIVE else None,
        "observation": observation,
        "writes_operacionais": observation.get("writes_operacionais", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow observer with explicit modes")
    parser.add_argument("--run-id", default=f"shadow-{uuid.uuid4()}")
    parser.add_argument("--mode", choices=sorted(SHADOW_MODES), default=DEFAULT_SHADOW_MODE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--frame", type=Path, default=DEFAULT_FRAME)
    parser.add_argument("--fixtures-dir", type=Path)
    parser.add_argument("--gateway-health", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Required only for gateway_read_only_live",
    )
    parser.add_argument(
        "--capture-mode",
        choices=("delivery_complete", "live_gateway"),
        default="live_gateway",
        help="delivery_complete uses coherent bundle anchor; live_gateway uses GET /packet",
    )
    parser.add_argument("--coherent-bundle", type=Path, help="Pre-captured coherent evaluation bundle JSON")
    parser.add_argument("--state-root", type=Path, help="Hermes state root for delivery_complete capture")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    health = read_json(args.gateway_health) if args.gateway_health and args.gateway_health.is_file() else None
    packet_doc = read_json(args.packet) if args.packet and args.packet.is_file() else None
    packet = packet_doc.get("packet") if isinstance(packet_doc, dict) and isinstance(packet_doc.get("packet"), dict) else packet_doc
    coherent_bundle = None
    if args.coherent_bundle and args.coherent_bundle.is_file():
        coherent_bundle = _load_coherent_capture().load_coherent_bundle(args.coherent_bundle)

    result = run_shadow_session(
        run_id=args.run_id,
        mode=args.mode,
        config_path=args.config,
        frame_path=args.frame,
        fixtures_dir=args.fixtures_dir,
        authorize=args.authorize,
        gateway_health=health,
        packet=packet,
        capture_mode=args.capture_mode,
        coherent_bundle=coherent_bundle,
        state_root=args.state_root,
    )

    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
