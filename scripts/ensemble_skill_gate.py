"""Fail-closed resolution of registry-declared Hermes skills.

The runner must prove that every declared skill is present in the canonical
profile, present in the forced Hermes home, byte-identical, and included in
Hermes' actual preload. Missing or partial specialty wiring is a hard stop.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any


SPECIALTY_MARKERS: dict[str, tuple[str, ...]] = {
    "topstep-smart-money": (
        "fair-value gaps",
        "displacement",
        "order blocks",
        "liquidity pools",
        "liquidity sweeps",
    ),
    "topstep-indicators": (
        "rsi",
        "macd",
        "atr",
        "divergences",
        "indicators as evidence",
    ),
}


class SkillPreloadError(RuntimeError):
    """Declared skills are missing, mismatched, or absent from preload."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical_profile_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_glitch_topstep_hermes_home() -> Path:
    """Force Hermes to the canonical checked-out profile, never ambient state."""
    configured = os.environ.get("GLITCH_TOPSTEP_CANONICAL_PROFILE", "").strip()
    root = Path(configured).expanduser().resolve() if configured else canonical_profile_root()
    return root


def resolve_profile_skill_path(profile_root: Path, skill_id: str) -> Path:
    return profile_root / "skills" / skill_id / "SKILL.md"


def ensure_skill_files_exist(
    skill_ids: list[str],
    *,
    profile_root: Path,
    hermes_home: Path,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        profile_path = resolve_profile_skill_path(profile_root, skill_id)
        live_path = hermes_home / "skills" / skill_id / "SKILL.md"
        if not profile_path.is_file():
            raise SkillPreloadError(f"skill_profile_missing:{skill_id}")
        if not live_path.is_file():
            raise SkillPreloadError(f"skill_hermes_home_missing:{skill_id}")
        profile_hash = sha256_file(profile_path)
        live_hash = sha256_file(live_path)
        if profile_hash != live_hash:
            raise SkillPreloadError(f"skill_hash_mismatch:{skill_id}")
        rows.append({
            "skill_id": skill_id,
            "profile_path": str(profile_path),
            "hermes_home_path": str(live_path),
            "sha256": profile_hash,
        })
    return {"hermes_home": str(hermes_home), "skills": rows}


def require_hermes_preload(skill_ids: list[str], *, hermes_home: Path) -> dict[str, Any]:
    agent_root = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"
    try:
        agent_available = agent_root.is_dir()
    except OSError as exc:
        raise SkillPreloadError(f"hermes_skill_api_unavailable:{type(exc).__name__}") from exc
    if agent_available and str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    previous = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(hermes_home)
    try:
        from agent.skill_commands import build_preloaded_skills_prompt  # type: ignore
        prompt, loaded, missing = build_preloaded_skills_prompt(list(skill_ids))
    except Exception as exc:  # noqa: BLE001
        raise SkillPreloadError(f"hermes_skill_api_unavailable:{type(exc).__name__}") from exc
    finally:
        if previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous
    expected = set(skill_ids)
    if missing or set(loaded) != expected:
        raise SkillPreloadError(
            "skill_preload_incomplete:loaded=" + ",".join(loaded)
            + ";missing=" + ",".join(missing)
        )
    lower = (prompt or "").lower()
    markers: dict[str, dict[str, bool]] = {}
    for skill_id, needles in SPECIALTY_MARKERS.items():
        if skill_id not in expected:
            continue
        markers[skill_id] = {needle: needle in lower for needle in needles}
        if not all(markers[skill_id].values()):
            raise SkillPreloadError(f"skill_preload_markers_missing:{skill_id}")
    return {
        "hermes_home": str(hermes_home),
        "loaded": loaded,
        "missing": missing,
        "prompt_len": len(prompt or ""),
        "prompt_sha256": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest().upper(),
        "specialty_markers": markers,
    }


def assert_declared_skills_ready(skill_ids: list[str], *, profile_root: Path) -> dict[str, Any]:
    hermes_home = default_glitch_topstep_hermes_home()
    files = ensure_skill_files_exist(
        skill_ids, profile_root=profile_root, hermes_home=hermes_home
    )
    return {"files": files, "preload": require_hermes_preload(skill_ids, hermes_home=hermes_home)}
