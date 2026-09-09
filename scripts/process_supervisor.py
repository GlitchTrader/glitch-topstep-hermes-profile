"""Hermes subprocess supervisor — identity-safe tree kill (audit C3 / Wave 0)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class LaunchIdentity:
    """Exact launch identity — never match by bare substring."""

    pid: int
    executable_path: str
    command_line: str
    argv: tuple[str, ...]
    parent_pid: int | None
    started_utc: str
    cwd: str | None = None
    launch_anchor: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_path(value: str | None) -> str:
    """Stable path key for identity compare (Windows + Linux CI fixtures)."""
    if not value:
        return ""
    # Preserve Windows drive literals on non-Windows runners (unit-test fixtures).
    compact = value.replace("\\", "/")
    if sys.platform != "win32" and len(compact) >= 2 and compact[1] == ":":
        return compact.lower()
    try:
        absolute = os.path.abspath(value)
    except (OSError, ValueError):
        absolute = value
    return os.path.normcase(absolute).replace("\\", "/")


def _paths_equal(left: str | None, right: str | None) -> bool:
    return _norm_path(left) == _norm_path(right)


def process_start_utc(pid: int) -> str | None:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_int <= 0 or sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid_int)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return (
            datetime.fromtimestamp((ticks - 116444736000000000) / 10_000_000, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def build_launch_identity(
    process: subprocess.Popen[str],
    command: Sequence[str],
    *,
    cwd: str | None = None,
    launch_anchor: str | None = None,
    parent_pid: int | None = None,
) -> LaunchIdentity:
    argv = tuple(str(part) for part in command)
    executable = _norm_path(argv[0]) if argv else ""
    try:
        pid_int = int(process.pid)
    except (TypeError, ValueError):
        pid_int = 0
    started = process_start_utc(pid_int) or _utc_now()
    return LaunchIdentity(
        pid=pid_int,
        executable_path=executable,
        command_line=subprocess.list2cmdline(list(argv)) if sys.platform == "win32" else " ".join(argv),
        argv=argv,
        parent_pid=os.getpid() if parent_pid is None else parent_pid,
        started_utc=started,
        cwd=_norm_path(cwd) if cwd else None,
        launch_anchor=launch_anchor,
    )


def identities_match(
    expected: LaunchIdentity,
    *,
    pid: int,
    executable_path: str | None,
    command_line: str | None,
    parent_pid: int | None,
    started_utc: str | None,
    cwd: str | None = None,
    start_skew_seconds: float = 30.0,
) -> bool:
    """Strict identity gate used before any terminate."""
    if int(pid) != int(expected.pid):
        return False
    if not process_is_alive(pid):
        return False
    if expected.executable_path and not _paths_equal(executable_path, expected.executable_path):
        return False
    if expected.command_line and (command_line or "") != expected.command_line:
        # Allow exact argv reconstruction mismatches only when argv tokens all present in order.
        if not command_line or not _argv_embedded_exactly(command_line, expected.argv):
            return False
    if expected.parent_pid is not None and parent_pid is not None:
        if int(parent_pid) != int(expected.parent_pid):
            # Parent may die after launch; accept only when recorded parent is dead AND
            # start time still matches (PID reuse protection remains via started_utc).
            if process_is_alive(int(expected.parent_pid)):
                return False
    if expected.started_utc and started_utc:
        try:
            exp = datetime.fromisoformat(expected.started_utc.replace("Z", "+00:00"))
            act = datetime.fromisoformat(started_utc.replace("Z", "+00:00"))
        except ValueError:
            return False
        if abs((exp - act).total_seconds()) > start_skew_seconds:
            return False
    if expected.cwd and cwd and not _paths_equal(cwd, expected.cwd):
        return False
    if expected.launch_anchor and command_line and expected.launch_anchor not in command_line:
        # Anchor must appear as a full path token, not an editor buffer substring alone.
        if f"{expected.launch_anchor}" not in command_line.replace("/", "\\") and \
           f"{expected.launch_anchor}" not in command_line.replace("\\", "/"):
            return False
        # Reject when the only hit is inside an unrelated editor path after a different root.
        if not _anchor_is_path_token(command_line, expected.launch_anchor):
            return False
    return True


def _argv_embedded_exactly(command_line: str, argv: Sequence[str]) -> bool:
    if not argv:
        return False
    cursor = 0
    lowered = command_line
    for token in argv:
        idx = lowered.find(token, cursor)
        if idx < 0:
            return False
        cursor = idx + len(token)
    return True


def _anchor_is_path_token(command_line: str, anchor: str) -> bool:
    variants = {anchor, anchor.replace("/", "\\"), anchor.replace("\\", "/")}
    for variant in variants:
        idx = command_line.find(variant)
        if idx < 0:
            continue
        before_ok = idx == 0 or command_line[idx - 1] in {" ", '"', "'", "="}
        end = idx + len(variant)
        after_ok = end >= len(command_line) or command_line[end] in {" ", '"', "'", "\\", "/"}
        if before_ok and after_ok:
            return True
    return False


def terminate_process_tree(process: subprocess.Popen[str], *, grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    parent_pgid: int | None = None
    if sys.platform != "win32":
        parent_pgid = os.getpgid(os.getpid())
    child_pgid: int | None = None
    if sys.platform != "win32":
        try:
            child_pgid = os.getpgid(process.pid)
        except (OSError, ProcessLookupError):
            child_pgid = None
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    elif child_pgid is not None and parent_pgid is not None and child_pgid != parent_pgid:
        try:
            os.killpg(child_pgid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
    else:
        process.terminate()
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    elif child_pgid is not None and parent_pgid is not None and child_pgid != parent_pgid:
        try:
            os.killpg(child_pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
    else:
        process.kill()


def terminate_pid_tree(
    pid: int,
    *,
    grace_seconds: float = 5.0,
    identity: LaunchIdentity | None = None,
    observed_executable: str | None = None,
    observed_command_line: str | None = None,
    observed_parent_pid: int | None = None,
    observed_started_utc: str | None = None,
    observed_cwd: str | None = None,
) -> bool:
    """Tree-kill only when identity matches; returns False when refused."""
    if pid <= 0:
        return False
    if identity is not None:
        if not identities_match(
            identity,
            pid=pid,
            executable_path=observed_executable,
            command_line=observed_command_line,
            parent_pid=observed_parent_pid,
            started_utc=observed_started_utc,
            cwd=observed_cwd,
        ):
            return False
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    parent_pgid: int | None = os.getpgid(os.getpid())
    child_pgid: int | None = None
    try:
        child_pgid = os.getpgid(pid)
    except (OSError, ProcessLookupError):
        child_pgid = None
    try:
        if child_pgid is not None and parent_pgid is not None and child_pgid != parent_pgid:
            os.killpg(child_pgid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.1)
    try:
        if child_pgid is not None and parent_pgid is not None and child_pgid != parent_pgid:
            os.killpg(child_pgid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    return True


def run_supervised(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    timeout_seconds: int,
    max_output_chars: int = 500_000,
    creationflags: int = 0,
    cwd: str | None = None,
    launch_anchor: str | None = None,
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
        cwd=cwd,
        start_new_session=sys.platform != "win32",
        creationflags=creationflags,
    )
    identity = build_launch_identity(
        process,
        command,
        cwd=cwd,
        launch_anchor=launch_anchor or (str(command[1]) if len(command) > 1 else None),
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        # Timeout path uses the Popen handle we launched — identity already bound to PID.
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
    # Keep identity available for callers via attribute for tests/debug.
    result = ProcessResult(returncode=process.returncode or 0, stdout=stdout, stderr=stderr)
    setattr(result, "launch_identity", identity)
    return result
