"""Fail-closed guards for canonical live stability — no wave0/.wt/external imports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

CANONICAL_ARTIFACT_SCHEMA = "glitch.topstep.canonical_live_stability.v1"
FORBIDDEN_PATH_MARKERS = (".wt-", "wave0-", "docs\\evidence", "docs/evidence")


class LiveRepoGuardError(RuntimeError):
    """Raised when live stability must not proceed."""


def git_head(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_is_forbidden_checkout(path: Path) -> bool:
    """Reject evidence dirs, wave0 parents, and .wt-* worktrees for live runs."""
    resolved = path.resolve()
    parts = [p.lower() for p in resolved.parts]
    joined = str(resolved).replace("/", "\\").lower()
    for part in parts:
        if part.startswith(".wt-") or part.startswith("wave0-"):
            return True
    for marker in FORBIDDEN_PATH_MARKERS:
        if marker.lower() in joined:
            return True
    return False


def assert_module_from_profile_root(module_file: str | Path, profile_root: Path) -> None:
    """Fail if an imported module resolves outside the profile checkout."""
    mod = Path(module_file).resolve()
    root = profile_root.resolve()
    try:
        mod.relative_to(root)
    except ValueError as exc:
        raise LiveRepoGuardError(f"import_outside_canonical_checkout:{mod}") from exc
    if path_is_forbidden_checkout(mod.parent) and path_is_forbidden_checkout(root):
        # Module under a forbidden tree when root itself is forbidden — live blocked separately.
        pass


def load_paired_contract_bytes(profile_root: Path) -> tuple[dict[str, Any], bytes]:
    path = profile_root / "paired-contract.json"
    if not path.is_file():
        raise LiveRepoGuardError("paired_contract_missing")
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def assert_paired_contract_match(profile_root: Path, gateway_root: Path) -> dict[str, Any]:
    profile_doc, profile_raw = load_paired_contract_bytes(profile_root)
    gw_path = gateway_root / "release" / "paired-contract.json"
    if not gw_path.is_file():
        raise LiveRepoGuardError("gateway_paired_contract_missing")
    gateway_raw = gw_path.read_bytes()
    if profile_raw != gateway_raw:
        raise LiveRepoGuardError("paired_contract_byte_mismatch")
    return profile_doc


def validate_live_repo_context(
    *,
    profile_root: Path,
    gateway_root: Path,
    expected_profile_sha: str | None = None,
    expected_gateway_sha: str | None = None,
    allow_worktree: bool = False,
) -> dict[str, Any]:
    """Validate roots + SHAs + paired contract before any live stability sampling."""
    profile_root = profile_root.resolve()
    gateway_root = gateway_root.resolve()

    if not allow_worktree and path_is_forbidden_checkout(profile_root):
        raise LiveRepoGuardError(f"forbidden_profile_checkout:{profile_root}")
    if not (profile_root / "scripts" / "operational_stability_gate.py").is_file():
        raise LiveRepoGuardError("profile_scripts_missing")
    if not (profile_root / "paired-contract.json").is_file():
        raise LiveRepoGuardError("profile_root_invalid")
    if not gateway_root.is_dir():
        raise LiveRepoGuardError("gateway_root_missing")

    profile_sha = git_head(profile_root)
    gateway_sha = git_head(gateway_root)
    if not profile_sha:
        raise LiveRepoGuardError("profile_sha_unreadable")
    if not gateway_sha:
        raise LiveRepoGuardError("gateway_sha_unreadable")

    expected_profile = (expected_profile_sha or os.environ.get("GLITCH_EXPECTED_PROFILE_SHA") or "").strip()
    expected_gateway = (expected_gateway_sha or os.environ.get("GLITCH_EXPECTED_GATEWAY_SHA") or "").strip()
    if expected_profile and not profile_sha.startswith(expected_profile) and profile_sha != expected_profile:
        raise LiveRepoGuardError(f"profile_sha_divergence:{profile_sha}:{expected_profile}")
    if expected_gateway and not gateway_sha.startswith(expected_gateway) and gateway_sha != expected_gateway:
        raise LiveRepoGuardError(f"gateway_sha_divergence:{gateway_sha}:{expected_gateway}")

    contract = assert_paired_contract_match(profile_root, gateway_root)
    gate_script = profile_root / "scripts" / "operational_stability_gate.py"
    runner_script = profile_root / "scripts" / "run-canonical-live-stability.py"
    assert_module_from_profile_root(gate_script, profile_root)

    return {
        "ok": True,
        "profile_root": str(profile_root),
        "gateway_root": str(gateway_root),
        "profile_sha": profile_sha,
        "gateway_sha": gateway_sha,
        "script_sha": {
            "operational_stability_gate.py": sha256_file(gate_script),
            "run-canonical-live-stability.py": (
                sha256_file(runner_script) if runner_script.is_file() else None
            ),
        },
        "paired_contract": {
            "gateway_version": (contract.get("gateway") or {}).get("version"),
            "profile_version": (contract.get("profile") or {}).get("version"),
            "prompt_version": (contract.get("profile") or {}).get("prompt_version"),
            "protocol_revision": contract.get("protocol_revision"),
            "sha256": hashlib.sha256((profile_root / "paired-contract.json").read_bytes()).hexdigest(),
        },
    }


_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def require_canonical_live_artifact_for_prac_soak(artifact: dict[str, Any] | None) -> None:
    """PRAC/soak must not start without a confirmed canonical live artifact + SHAs."""
    if not isinstance(artifact, dict):
        raise LiveRepoGuardError("canonical_live_artifact_missing")
    if artifact.get("schema_version") != CANONICAL_ARTIFACT_SCHEMA:
        raise LiveRepoGuardError("canonical_live_artifact_schema_invalid")
    if artifact.get("confirmed") is not True:
        raise LiveRepoGuardError("canonical_live_artifact_not_confirmed")
    if artifact.get("canonical_entry") is not True:
        raise LiveRepoGuardError("canonical_live_entry_missing")
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    for key in ("profile_sha", "gateway_sha"):
        sha = str(provenance.get(key) or "")
        if not _SHA_RE.match(sha):
            raise LiveRepoGuardError(f"canonical_live_artifact_{key}_missing")
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), dict) else {}
    if int(safety.get("intents_sent") or 0) != 0:
        raise LiveRepoGuardError("canonical_live_artifact_had_intents")
    if int(safety.get("orders_sent") or 0) != 0:
        raise LiveRepoGuardError("canonical_live_artifact_had_orders")
    if int(safety.get("writes_operacionais") or 0) != 0:
        raise LiveRepoGuardError("canonical_live_artifact_had_writes")
