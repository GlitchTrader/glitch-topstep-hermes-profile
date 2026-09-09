"""Canonical live stability runner - scripts/ only; no evidence-dir ad-hoc scripts.

Validates profile/gateway roots, SHAs, and paired contract, then runs a single shared-clock
bar-close stability window. Never calls wait_for_bar_complete first.
Read-only: zero intents / orders / operational writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import utc_now  # noqa: E402
from live_stability_repo_guard import (  # noqa: E402
    CANONICAL_ARTIFACT_SCHEMA,
    LiveRepoGuardError,
    assert_module_from_profile_root,
    path_is_forbidden_checkout,
    validate_live_repo_context,
)
from operational_stability_gate import (  # noqa: E402
    CANONICAL_LIVE_STABILITY_ENTRY,
    run_canonical_live_stability_window,
    write_stability_artifact,
)
from quote_state import classify_evaluation_axes  # noqa: E402


def default_gateway_root() -> Path:
    env = os.environ.get("GLITCH_GATEWAY_ROOT", "").strip()
    if env:
        return Path(env)
    sibling = REPO.parent / "glitch-topstep"
    if sibling.is_dir():
        return sibling
    raise LiveRepoGuardError("set_GLITCH_GATEWAY_ROOT")


def default_profile_root() -> Path:
    env = os.environ.get("GLITCH_HERMES_PROFILE_ROOT", "").strip()
    return Path(env) if env else REPO


def _readonly_fetchers(base_url: str, token: str):
    import urllib.error
    import urllib.request

    def _get(path: str) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health() -> dict[str, Any]:
        return _get("/health")

    def packet() -> dict[str, Any]:
        return _get("/hermes/packet")

    return health, packet


def build_canonical_artifact(
    *,
    stability: dict[str, Any],
    provenance: dict[str, Any],
    evaluation_axes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_ARTIFACT_SCHEMA,
        "generated_utc": utc_now(),
        "canonical_entry": True,
        "canonical_live_entry": CANONICAL_LIVE_STABILITY_ENTRY,
        "shared_clock": True,
        "pre_wait_forbidden": True,
        "confirmed": bool(stability.get("confirmed")),
        "classification": stability.get("classification"),
        "stop_reason": stability.get("stop_reason"),
        "stability": stability,
        "evaluation_axes": evaluation_axes,
        "provenance": {
            "profile_root": provenance.get("profile_root"),
            "gateway_root": provenance.get("gateway_root"),
            "profile_sha": provenance.get("profile_sha"),
            "gateway_sha": provenance.get("gateway_sha"),
            "script_sha": provenance.get("script_sha"),
            "paired_contract": provenance.get("paired_contract"),
        },
        "safety": {
            "execution_authority": False,
            "intents_sent": 0,
            "orders_sent": 0,
            "writes_operacionais": 0,
            "mutation_endpoints_called": [],
        },
    }


def axes_from_stability(stability: dict[str, Any]) -> dict[str, Any] | None:
    samples = stability.get("samples") or []
    if not samples:
        return None
    last = samples[-1]
    detail = last.get("detail") if isinstance(last.get("detail"), dict) else {}
    # Reconstruct minimal health/packet views from sample detail when present.
    health = {
        "data_quality": {
            "quote_state": detail.get("quote_state"),
            "issues": detail.get("health_issues") or [],
            "state_complete": detail.get("health_state_complete"),
            "execution_eligibility": detail.get("execution_eligibility"),
        }
    }
    packet = {
        "data_quality": {
            "quote_state": detail.get("quote_state"),
            "issues": detail.get("packet_issues") or [],
            "state_complete": detail.get("packet_state_complete"),
            "execution_eligibility": detail.get("execution_eligibility"),
        },
        "market": detail.get("market") or {},
    }
    return classify_evaluation_axes(health, packet)


def run_guarded_canonical_stability(
    *,
    profile_root: Path,
    gateway_root: Path,
    health_fetcher,
    packet_fetcher,
    expected_profile_sha: str | None = None,
    expected_gateway_sha: str | None = None,
    allow_worktree: bool = False,
    out_path: Path | None = None,
) -> dict[str, Any]:
    assert_module_from_profile_root(__file__, profile_root)
    assert_module_from_profile_root(
        profile_root / "scripts" / "operational_stability_gate.py",
        profile_root,
    )
    provenance = validate_live_repo_context(
        profile_root=profile_root,
        gateway_root=gateway_root,
        expected_profile_sha=expected_profile_sha,
        expected_gateway_sha=expected_gateway_sha,
        allow_worktree=allow_worktree,
    )
    stability = run_canonical_live_stability_window(
        health_fetcher=health_fetcher,
        packet_fetcher=packet_fetcher,
    )
    artifact = build_canonical_artifact(
        stability=stability,
        provenance=provenance,
        evaluation_axes=axes_from_stability(stability),
    )
    if out_path is not None:
        write_stability_artifact(out_path, artifact)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, default=None)
    parser.add_argument("--gateway-root", type=Path, default=None)
    parser.add_argument("--expected-profile-sha", default=os.environ.get("GLITCH_EXPECTED_PROFILE_SHA"))
    parser.add_argument("--expected-gateway-sha", default=os.environ.get("GLITCH_EXPECTED_GATEWAY_SHA"))
    parser.add_argument("--gateway-url", default=os.environ.get("GLITCH_GATEWAY_URL", "http://127.0.0.1:8790"))
    parser.add_argument("--token", default=os.environ.get("GLITCH_LOCAL_TOKEN", ""))
    parser.add_argument("--out", type=Path, required=False)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually sample the live gateway (read-only). Without this flag only validates context.",
    )
    parser.add_argument(
        "--allow-worktree",
        action="store_true",
        help="Dangerous: allow .wt-/wave0 checkouts (tests only).",
    )
    args = parser.parse_args(argv)

    profile_root = (args.profile_root or default_profile_root()).resolve()
    try:
        gateway_root = (args.gateway_root or default_gateway_root()).resolve()
    except LiveRepoGuardError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    if not args.allow_worktree and path_is_forbidden_checkout(profile_root):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"forbidden_profile_checkout:{profile_root}",
                    "hint": "Use an installed/canonical profile checkout, not .wt-* or wave0-*.",
                },
                indent=2,
            )
        )
        return 2

    try:
        provenance = validate_live_repo_context(
            profile_root=profile_root,
            gateway_root=gateway_root,
            expected_profile_sha=args.expected_profile_sha,
            expected_gateway_sha=args.expected_gateway_sha,
            allow_worktree=args.allow_worktree,
        )
    except LiveRepoGuardError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    if not args.execute:
        report = {
            "ok": True,
            "dry_run": True,
            "message": "context_validated_execute_not_requested",
            "provenance": provenance,
        }
        print(json.dumps(report, indent=2))
        return 0

    if not args.token:
        print(json.dumps({"ok": False, "error": "GLITCH_LOCAL_TOKEN_required"}, indent=2))
        return 2

    health, packet = _readonly_fetchers(args.gateway_url, args.token)
    out = args.out or (profile_root / "evaluation" / "runs" / f"canonical-live-stability-{utc_now().replace(':', '')}.json")
    try:
        artifact = run_guarded_canonical_stability(
            profile_root=profile_root,
            gateway_root=gateway_root,
            health_fetcher=health,
            packet_fetcher=packet,
            expected_profile_sha=args.expected_profile_sha,
            expected_gateway_sha=args.expected_gateway_sha,
            allow_worktree=args.allow_worktree,
            out_path=out,
        )
    except LiveRepoGuardError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    print(json.dumps({"ok": True, "out": str(out), "confirmed": artifact.get("confirmed")}, indent=2))
    return 0 if artifact.get("confirmed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
