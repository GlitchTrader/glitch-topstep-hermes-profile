"""Phase 7 shadow live preflight — prepares readiness without starting gateway/Hermes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import read_json, utc_now  # noqa: E402
from evaluation_owner import (  # noqa: E402
    bootstrap_evaluation_hermes_home,
    ensure_evaluation_auth_ready,
    evaluation_hermes_home,
    is_forbidden_production_path,
    load_evaluation_budget,
    production_lane_active,
    production_profile_root,
    production_state_root,
)

import importlib.util

PREFLIGHT_SCHEMA = "glitch.topstep.shadow_preflight.v1"
DEFAULT_CONFIG = REPO / "evaluation" / "shadow-live-run-config.v1.json"
DEFAULT_PACKAGE = REPO / "evaluation" / "release" / "six-profile-evaluation-package-2026-09-02.json"


def _load_measurement_ready():
    spec = importlib.util.spec_from_file_location(
        "evaluation_measurement_ready", SCRIPTS / "evaluation-measurement-ready.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_replay_preflight():
    spec = importlib.util.spec_from_file_location(
        "preflight_evaluation_replay", SCRIPTS / "preflight-evaluation-replay.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_lease():
    spec = importlib.util.spec_from_file_location("evaluation_lease", SCRIPTS / "evaluation_lease.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_package_pins(package: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for rel_path, expected in (package.get("file_hashes") or {}).items():
        actual_path = REPO / rel_path
        if not actual_path.is_file():
            issues.append(f"missing:{rel_path}")
            continue
        actual = _sha256_file(actual_path)
        if actual != expected:
            issues.append(f"hash_drift:{rel_path}")
    return not issues, issues


def shadow_preflight(
    *,
    run_id: str,
    config_path: Path = DEFAULT_CONFIG,
    package_path: Path | None = DEFAULT_PACKAGE,
    gateway_health: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
    fetch_gateway: bool = False,
) -> dict[str, Any]:
    """Return shadow readiness without starting gateway, Hermes, or live session."""
    config = read_json(config_path)
    registry = read_json(REPO / "evaluation" / "registry.json")
    ensemble_config = read_json(REPO / "evaluation" / "ensemble_config.json")
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []

    measurement = _load_measurement_ready()
    mr = measurement.evaluation_measurement_ready(
        mode="preflight",
        packet=packet,
        gateway_health=gateway_health,
    )
    checks.append({"id": "measurement_ready", "ok": mr.get("ready"), "detail": mr})
    blocking.extend(mr.get("blocking_reasons") or [])

    if packet is not None:
        capture_mr = measurement.evaluation_measurement_ready(
            mode="capture",
            packet=packet,
            gateway_health=gateway_health,
        )
        checks.append({"id": "capture_readiness", "ok": capture_mr.get("ready"), "detail": capture_mr})
        for reason in capture_mr.get("blocking_reasons") or []:
            if reason not in blocking:
                blocking.append(reason)

    if fetch_gateway:
        checks.append(
            {
                "id": "fetch_gateway_blocked_in_prep",
                "ok": False,
                "detail": "fetch_gateway requires explicit live authorization",
            }
        )
        blocking.append("live_fetch_requires_authorization")

    replay = _load_replay_preflight().preflight_evaluation_replay(
        run_id=run_id,
        scenarios_path=REPO / "evaluation" / "shadow-live-scenarios.v1.json",
    )
    checks.append({"id": "evaluation_replay_coordination", "ok": replay.get("ok"), "detail": replay})

    lease_mod = _load_lease()
    prod_state = production_state_root()
    lease = lease_mod.read_evaluation_lease(prod_state)
    lease_active = lease_mod.evaluation_lease_active(prod_state)
    foreign_lease = lease_active and str((lease or {}).get("run_id") or "") != run_id
    if foreign_lease:
        checks.append({"id": "lease_available", "ok": False, "detail": lease})
        blocking.append("lease_occupied")
    else:
        checks.append({"id": "lease_available", "ok": True, "detail": "no_foreign_lease"})

    lane_active = production_lane_active(production_state=prod_state)
    cron_defer_ok = (not lane_active) or replay.get("ok")
    checks.append(
        {
            "id": "cron_defer",
            "ok": cron_defer_ok,
            "detail": {"lane_active": lane_active, "coordination_ok": replay.get("ok")},
        }
    )
    if not cron_defer_ok:
        blocking.append("cron_active_without_coordination")

    home = evaluation_hermes_home()
    bootstrap_evaluation_hermes_home()
    auth_ok, auth_err = ensure_evaluation_auth_ready(home)
    checks.append(
        {
            "id": "hermes_home_isolated",
            "ok": home.resolve() != production_profile_root().resolve(),
            "detail": {"evaluation": str(home), "production": str(production_profile_root())},
        }
    )
    checks.append(
        {
            "id": "evaluation_credentials",
            "ok": auth_ok,
            "detail": {"hermes_home": str(home), "error": auth_err or None},
        }
    )
    if not auth_ok:
        blocking.append("hermes_auth_not_ready")

    forbidden_ok = all(is_forbidden_production_path(REPO / p) for p in ("state/outbox", "state/receipts.jsonl"))
    checks.append({"id": "production_paths_protected", "ok": forbidden_ok})

    enabled_profiles = [p for p in registry.get("profiles") or [] if p.get("enabled", True)]
    exec_auth_ok = all(not p.get("execution_authority", False) for p in enabled_profiles)
    checks.append(
        {
            "id": "execution_authority_false_all",
            "ok": exec_auth_ok and len(enabled_profiles) == 6,
            "detail": [p.get("profile_id") for p in enabled_profiles],
        }
    )
    if not exec_auth_ok:
        blocking.append("execution_authority_present")

    budget = load_evaluation_budget()
    cost_cap = float((config.get("budget") or {}).get("max_cost_usd_per_session") or budget.get("max_cost_usd_per_session") or 0)
    checks.append({"id": "cost_budget_known", "ok": cost_cap > 0, "detail": cost_cap})
    if cost_cap <= 0:
        blocking.append("cost_unknown")

    checks.append(
        {
            "id": "production_parallelism_blocked",
            "ok": ensemble_config.get("status") != "production_enabled",
            "detail": ensemble_config.get("status"),
        }
    )
    checks.append(
        {
            "id": "promotion_use_allowed_false",
            "ok": registry.get("promotion_status") == "blocked",
            "detail": registry.get("promotion_status"),
        }
    )

    if package_path and package_path.is_file():
        package = read_json(package_path)
        pins_ok, pin_issues = _verify_package_pins(package)
        checks.append({"id": "release_package_pins", "ok": pins_ok, "detail": pin_issues})
        if not pins_ok:
            blocking.append("release_package_hash_drift")
    else:
        checks.append({"id": "release_package_pins", "ok": False, "detail": "package_missing"})
        blocking.append("release_package_missing")

    blocking_unique = sorted(set(blocking))
    ready = len(blocking_unique) == 0 and replay.get("ok")

    if "maintenance_window" in blocking_unique:
        status = "shadow_not_ready:maintenance_window"
    elif ready:
        status = "shadow_ready"
    elif blocking_unique:
        status = f"shadow_not_ready:{blocking_unique[0]}"
    else:
        status = "shadow_not_ready:preflight_failed"

    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "shadow_live_execution_authorized": False,
        "gateway_started": False,
        "hermes_started": False,
        "ready": ready,
        "status": status,
        "blocking_reasons": blocking_unique,
        "checks": checks,
        "promotion_use_allowed": False,
        "production_parallelism": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 shadow live preflight (no gateway/Hermes start)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--gateway-health", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    health = read_json(args.gateway_health) if args.gateway_health and args.gateway_health.is_file() else None
    packet_doc = read_json(args.packet) if args.packet and args.packet.is_file() else None
    packet = packet_doc.get("packet") if isinstance(packet_doc, dict) and isinstance(packet_doc.get("packet"), dict) else packet_doc

    result = shadow_preflight(
        run_id=args.run_id,
        config_path=args.config,
        package_path=args.package,
        gateway_health=health,
        packet=packet,
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
