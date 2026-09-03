"""Preflight for Trilha A first real Hermes controlled execution (evaluation lane only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import importlib.util

from common import read_json  # noqa: E402
from ensemble_envelope_seal import (  # noqa: E402
    assert_sealed_envelope_matches_pin,
    seal_envelope_from_pin,
    seal_envelope_from_run_config,
    sealed_envelope_identity,
)
from evaluation_owner import (  # noqa: E402
    bootstrap_evaluation_hermes_home,
    ensure_evaluation_auth_ready,
    evaluation_auth_mode,
    evaluation_hermes_home,
    is_forbidden_production_path,
    load_evaluation_budget,
    production_lane_active,
    production_profile_root,
    production_state_root,
)

_PREFLIGHT_REPLAY_SPEC = importlib.util.spec_from_file_location(
    "preflight_evaluation_replay", SCRIPTS / "preflight-evaluation-replay.py"
)
assert _PREFLIGHT_REPLAY_SPEC and _PREFLIGHT_REPLAY_SPEC.loader
_PREFLIGHT_REPLAY = importlib.util.module_from_spec(_PREFLIGHT_REPLAY_SPEC)
sys.modules["preflight_evaluation_replay"] = _PREFLIGHT_REPLAY
_PREFLIGHT_REPLAY_SPEC.loader.exec_module(_PREFLIGHT_REPLAY)
preflight_evaluation_replay = _PREFLIGHT_REPLAY.preflight_evaluation_replay

PREFLIGHT_SCHEMA = "glitch.topstep.trail_a_real_preflight.v1"
MULTI_PREFLIGHT_SCHEMA = "glitch.topstep.trail_a_multi_envelope_preflight.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "trail-a-real-run-config.v1.json"
DEFAULT_SCENARIOS = REPO / "evaluation" / "trail-a-real-scenarios.v1.json"
DEFAULT_MULTI_CONFIG = REPO / "evaluation" / "trail-a-multi-envelope-run-config.v1.json"
DEFAULT_MULTI_SCENARIOS = REPO / "evaluation" / "trail-a-multi-envelope-scenarios.v1.json"
COHORT_REGISTRY = REPO / "evaluation" / "runs" / "stratified-cohort-execution-registry.json"


def is_multi_envelope_config(config: dict[str, Any]) -> bool:
    schema = str(config.get("schema_version") or "")
    if "multi_envelope" in schema:
        return True
    return isinstance(config.get("envelopes"), list) and len(config.get("envelopes") or []) > 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pinned_envelope(
    *,
    config: dict[str, Any],
    scenarios: dict[str, Any],
    matrix: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    env_cfg = config.get("envelope") or {}
    frame_path = REPO / str(env_cfg.get("frame_path") or "")
    issues: list[str] = []
    if not frame_path.is_file():
        return {"ok": False, "issues": ["frame_missing"], "frame_path": str(frame_path)}

    actual_frame_sha = _sha256_file(frame_path)
    expected_frame_sha = str(env_cfg.get("frame_sha256") or "")
    if actual_frame_sha != expected_frame_sha:
        issues.append("frame_sha256_mismatch")

    built = seal_envelope_from_run_config(config=config, matrix=matrix, mapping=mapping, repo=REPO)
    snap = str(built.get("snapshot_hash") or "")
    identity = sealed_envelope_identity(built)
    eh = str(identity.get("envelope_hash") or "")
    issues.extend(assert_sealed_envelope_matches_pin(built, env_cfg))

    scenario = (scenarios.get("scenarios") or [{}])[0]
    for key in ("snapshot_hash", "envelope_hash", "frame_id"):
        if str(scenario.get(key) or "") != str(env_cfg.get(key if key != "frame_id" else "frame_id") or ""):
            issues.append(f"scenario_config_{key}_mismatch")

    return {
        "ok": not issues,
        "issues": issues,
        "frame_path": str(frame_path),
        "computed": {
            "snapshot_hash": snap,
            "envelope_hash": eh,
            "envelope_id": built.get("envelope_id"),
            "validity_seconds": identity.get("validity_seconds"),
            "frame_sha256": actual_frame_sha,
        },
    }


def validate_pinned_envelopes(
    *,
    config: dict[str, Any],
    scenarios: dict[str, Any],
    matrix: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    envelope_pins = list(config.get("envelopes") or [])
    scenario_rows = list(scenarios.get("scenarios") or [])
    issues: list[str] = []
    computed: list[dict[str, Any]] = []
    if len(envelope_pins) < 2:
        issues.append("multi_envelope_count_below_minimum")
    if len(envelope_pins) != len(scenario_rows):
        issues.append("envelope_scenario_count_mismatch")
    scenario_by_id = {str(s.get("scenario_id") or ""): s for s in scenario_rows}
    seen_snapshot: set[str] = set()
    seen_envelope: set[str] = set()
    for pin in envelope_pins:
        scenario_id = str(pin.get("scenario_id") or "")
        scenario = scenario_by_id.get(scenario_id)
        if scenario is None:
            issues.append(f"scenario_missing:{scenario_id}")
            continue
        frame_path = REPO / str(pin.get("frame_path") or "")
        if not frame_path.is_file():
            issues.append(f"frame_missing:{scenario_id}")
            continue
        actual_frame_sha = _sha256_file(frame_path)
        if actual_frame_sha != str(pin.get("frame_sha256") or ""):
            issues.append(f"frame_sha256_mismatch:{scenario_id}")
        built = seal_envelope_from_pin(
            envelope_pin=pin,
            config=config,
            matrix=matrix,
            mapping=mapping,
            repo=REPO,
        )
        identity = sealed_envelope_identity(built)
        issues.extend(f"{issue}:{scenario_id}" for issue in assert_sealed_envelope_matches_pin(built, pin))
        for key in ("snapshot_hash", "envelope_hash", "frame_id", "envelope_id"):
            if str(scenario.get(key) or "") != str(pin.get(key) or ""):
                issues.append(f"scenario_config_{key}_mismatch:{scenario_id}")
        snap = str(identity.get("snapshot_hash") or "")
        eh = str(identity.get("envelope_hash") or "")
        if snap in seen_snapshot and eh not in seen_envelope:
            issues.append(f"snapshot_reuse_with_different_envelope:{scenario_id}")
        seen_snapshot.add(snap)
        seen_envelope.add(eh)
        computed.append(
            {
                "scenario_id": scenario_id,
                "frame_id": pin.get("frame_id"),
                "snapshot_hash": snap,
                "envelope_hash": eh,
                "envelope_id": built.get("envelope_id"),
                "validity_seconds": identity.get("validity_seconds"),
                "frame_sha256": actual_frame_sha,
            }
        )
    return {"ok": not issues, "issues": issues, "envelopes": computed}


def run_trail_a_real_preflight(
    *,
    run_id: str,
    config_path: Path = DEFAULT_CONFIG,
    scenarios_path: Path = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    config = read_json(config_path)
    scenarios = read_json(scenarios_path)
    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    budget = load_evaluation_budget(REPO / "evaluation" / "ensemble_config.json")

    checks: list[dict[str, Any]] = []

    replay_preflight = preflight_evaluation_replay(run_id=run_id, scenarios_path=scenarios_path)
    checks.append({"id": "evaluation_replay_preflight", "ok": replay_preflight.get("ok"), "detail": replay_preflight})

    multi = is_multi_envelope_config(config)
    if multi:
        envelope_check = validate_pinned_envelopes(
            config=config, scenarios=scenarios, matrix=matrix, mapping=mapping
        )
        checks.append({"id": "pinned_envelope_digests", "ok": envelope_check["ok"], "detail": envelope_check})
    else:
        envelope_check = validate_pinned_envelope(config=config, scenarios=scenarios, matrix=matrix, mapping=mapping)
        checks.append({"id": "pinned_envelope_digest", "ok": envelope_check["ok"], "detail": envelope_check})

    home = evaluation_hermes_home()
    bootstrap_evaluation_hermes_home()
    auth_ok, auth_err = ensure_evaluation_auth_ready(home)
    checks.append(
        {
            "id": "evaluation_credentials",
            "ok": auth_ok,
            "detail": {"mode": evaluation_auth_mode(), "hermes_home": str(home), "error": auth_err or None},
        }
    )

    prod_root = production_profile_root()
    eval_home = evaluation_hermes_home()
    checks.append(
        {
            "id": "hermes_home_isolated",
            "ok": eval_home.resolve() != prod_root.resolve(),
            "detail": {"evaluation": str(eval_home), "production": str(prod_root)},
        }
    )

    forbidden_ok = all(
        is_forbidden_production_path(Path(p))
        for p in ("state/outbox", "state/receipts.jsonl", "state/decisions.jsonl")
    )
    checks.append({"id": "production_paths_protected", "ok": forbidden_ok})

    lane = production_lane_active(production_state=production_state_root())
    checks.append(
        {
            "id": "production_lane",
            "ok": True,
            "detail": "lane_active defers replay; lease defers cron when LIVE_VALIDATED",
            "lane_active": lane,
        }
    )

    enabled = {str(p["profile_id"]) for p in registry.get("profiles") or [] if p.get("enabled", True)}
    expected_profiles = {str(p) for p in scenarios.get("profiles") or []}
    profiles_ok = expected_profiles <= enabled
    checks.append(
        {
            "id": "profiles_registered",
            "ok": profiles_ok,
            "detail": {"expected": sorted(expected_profiles), "enabled": sorted(enabled)},
        }
    )

    slots = int((config.get("budget") or {}).get("max_parallel_slots") or 2)
    checks.append({"id": "max_parallel_slots", "ok": slots == 2, "detail": slots})

    cost_cap = float((config.get("budget") or {}).get("max_cost_usd_per_session") or budget.get("max_cost_usd_per_session") or 2.5)
    checks.append({"id": "cost_budget_known", "ok": cost_cap > 0, "detail": cost_cap})

    offline_acceptance = REPO / "evaluation" / "runs" / "trail-a-acceptance-report-2026-09-02.json"
    offline_ok = False
    if offline_acceptance.is_file():
        offline_doc = read_json(offline_acceptance)
        offline_ok = offline_doc.get("verdict") == "PASS"
    checks.append(
        {
            "id": "trail_a_offline_acceptance",
            "ok": offline_ok,
            "detail": str(offline_acceptance),
        }
    )

    timeout_ms = int((config.get("budget") or {}).get("per_profile_timeout_ms") or budget.get("per_profile_timeout_ms") or 35000)
    checks.append({"id": "per_profile_timeout", "ok": timeout_ms > 0, "detail": timeout_ms})

    registry_path = COHORT_REGISTRY if COHORT_REGISTRY.is_file() else REPO / "evaluation" / "registry.json"
    cohort_reg = read_json(registry_path) if registry_path.is_file() else {}
    next_run = cohort_reg.get("next_authorized_run_id")
    checks.append(
        {
            "id": "directional_next_authorized_run_id_null",
            "ok": next_run is None,
            "detail": {"next_authorized_run_id": next_run, "source": str(registry_path)},
        }
    )

    if multi:
        auth_path = REPO / "evaluation" / "reviews" / "TRAIL-A-MULTI-ENVELOPE-AUTHORIZATION.md"
        manifest_path = REPO / "evaluation" / "trail-a-multi-envelope-manifest.v1.json"
        auth_ok = auth_path.is_file() and manifest_path.is_file()
        checks.append(
            {
                "id": "multi_envelope_authorization_artifacts",
                "ok": auth_ok,
                "detail": {"authorization": str(auth_path), "manifest": str(manifest_path)},
            }
        )
        expected_run = str(config.get("authorized_run_id") or run_id)
        checks.append(
            {
                "id": "authorized_run_id_matches",
                "ok": expected_run == run_id,
                "detail": expected_run,
            }
        )

    blocking = [c for c in checks if not c.get("ok") and c["id"] not in {"production_lane"}]
    ok = len(blocking) == 0 and replay_preflight.get("ok")

    return {
        "schema_version": MULTI_PREFLIGHT_SCHEMA if multi else PREFLIGHT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "multi_envelope": multi,
        "verdict": "PASS" if ok else "FAIL",
        "ready_for_human_authorization": ok,
        "hermes_execution_authorized": False,
        "checks": checks,
        "pinned_envelope": config.get("envelope"),
        "pinned_envelopes": config.get("envelopes") if multi else None,
        "budget": config.get("budget"),
        "blocked_modes": config.get("blocked"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trilha A real Hermes run preflight")
    parser.add_argument("--run-id", default="trail-a-real-2026-09-02")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "evaluation" / "runs" / "trail-a-real-preflight-report.json",
    )
    args = parser.parse_args()

    report = run_trail_a_real_preflight(
        run_id=args.run_id,
        config_path=args.config,
        scenarios_path=args.scenarios,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(args.output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
