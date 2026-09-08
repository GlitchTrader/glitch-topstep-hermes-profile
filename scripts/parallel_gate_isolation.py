"""Per-task isolation for parallel gate runners — exclusive HERMES_HOME, GLITCH_DATA_DIR, leases."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from evaluation_owner import _tolerant_rmtree, bootstrap_evaluation_hermes_home

EVALUATION_PROFILE_SUFFIX = "glitch-topstep-evaluation"


def prepare_isolated_gate_env(
    task_id: str,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return subprocess env with exclusive evaluation home + data dir per task."""
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in task_id)
    prefix = f"gate-{safe_id}-{uuid.uuid4().hex[:8]}-"
    work_root = Path(tempfile.mkdtemp(prefix=prefix))
    eval_home = work_root / EVALUATION_PROFILE_SUFFIX
    data_dir = work_root / "data"
    metadata: dict[str, Any] = {}
    bootstrap_evaluation_hermes_home(target=eval_home, metadata=metadata)
    data_dir.mkdir(parents=True, exist_ok=True)

    env = dict(base_env or os.environ)
    env["EVALUATION_HERMES_HOME"] = str(eval_home)
    env["HERMES_HOME"] = str(eval_home)
    env["GLITCH_DATA_DIR"] = str(data_dir)
    context = {
        "task_id": task_id,
        "work_root": work_root,
        "eval_home": eval_home,
        "data_dir": data_dir,
        "cleanup_deferred": list(metadata.get("cleanup_deferred") or []),
    }
    return env, context


def cleanup_isolated_gate(context: dict[str, Any]) -> list[str]:
    """Safe Windows cleanup; returns paths that could not be removed."""
    deferred = list(context.get("cleanup_deferred") or [])
    work_root = context.get("work_root")
    if work_root is not None:
        deferred.extend(_tolerant_rmtree(Path(work_root)))
    return deferred


def aggregate_parallel_results(results: list[dict[str, Any]], *, exit_key: str = "exit_code") -> dict[str, Any]:
    """Fail closed: any non-zero exit or missing exit_code => all_pass false."""
    all_pass = True
    for row in results:
        code = row.get(exit_key)
        if code is None or code != 0:
            all_pass = False
            break
    return {
        "task_count": len(results),
        "all_pass": all_pass,
        "failed_tasks": [r.get("task_id") or r.get("gate_id") or r.get("check_id") for r in results if r.get(exit_key) != 0],
    }
