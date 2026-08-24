"""Hermes subprocess supervisor — tree kill on timeout before ownership release (audit C3)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def terminate_process_tree(process: subprocess.Popen[str], *, grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.1)
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()


def run_supervised(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    timeout_seconds: int,
    max_output_chars: int = 500_000,
    creationflags: int = 0,
) -> ProcessResult:
    """Run a subprocess and confirm termination before returning."""
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=sys.platform != "win32",
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process)
            process.wait(timeout=5)
        raise RuntimeError("hermes_timeout") from None
    if len(stdout) > max_output_chars:
        stdout = stdout[:max_output_chars]
    if len(stderr) > max_output_chars:
        stderr = stderr[:max_output_chars]
    return ProcessResult(returncode=process.returncode or 0, stdout=stdout, stderr=stderr)
