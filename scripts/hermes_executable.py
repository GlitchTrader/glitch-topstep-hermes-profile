"""Resolve the host Hermes CLI without relying on PATH alone."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_hermes_executable() -> str:
    """Resolve configured or official host Hermes installation.

    Order: HERMES_EXECUTABLE → PATH (`shutil.which`) →
    `%LOCALAPPDATA%/hermes/hermes-agent/venv/Scripts/hermes.exe`.
    """
    configured = os.environ.get("HERMES_EXECUTABLE", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    path_candidate = shutil.which("hermes")
    if path_candidate:
        candidates.append(Path(path_candidate))
    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        candidates.append(
            Path(local_app) / "hermes" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
        )
    seen: set[str] = set()
    path_candidate_text = str(path_candidate) if path_candidate else ""
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
            exists = candidate.is_file()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if exists or (path_candidate_text and str(candidate) == path_candidate_text):
            return resolved
    raise RuntimeError("hermes_executable_not_found")
