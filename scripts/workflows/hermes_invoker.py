"""Supervised Hermes CLI invocation for learning loops (audit C1)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import extract_single_json_object, hermes_chat_model_cli_args, profile_root
from process_supervisor import run_supervised

from hermes_toolsets import DEFAULT_HERMES_TOOLSETS

LEARNING_SOURCE = "trading"


def invoke_learning_hermes(
    profile: str,
    prompt: str,
    skills: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    python_executable = Path(executable).with_name(
        "python.exe" if sys.platform == "win32" else "python"
    )
    if not python_executable.is_file():
        python_executable = Path(sys.executable)
    root = profile_root(profile)
    args = [
        "chat", "-Q", "--source", LEARNING_SOURCE,
        *hermes_chat_model_cli_args(
            root,
            model_env="GLITCH_TOPSTEP_CORE_MODEL",
            provider_env="GLITCH_TOPSTEP_CORE_PROVIDER",
        ),
        "--max-turns", "8", "--skills", skills,
        "--toolsets", DEFAULT_HERMES_TOOLSETS,
    ]
    wrapper = (
        "import os,sys;from pathlib import Path;"
        "os.environ['HERMES_HOME']=str(Path.home()/'AppData'/'Local'/'hermes'/'profiles'/"
        + repr(profile)
        + ");from hermes_cli.main import main;prompt=sys.stdin.read();"
        "sys.argv=[sys.argv[0]]+" + repr(args) + "+['-q',prompt];main()"
    )
    completed = run_supervised(
        [str(python_executable), "-c", wrapper],
        input_text=prompt,
        timeout_seconds=timeout_seconds,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"hermes_failed:{completed.returncode}:{completed.stderr.strip()[:400]}"
        )
    return extract_single_json_object(
        completed.stdout,
        schema="glitch.topstep.learning_output.v1",
    )
