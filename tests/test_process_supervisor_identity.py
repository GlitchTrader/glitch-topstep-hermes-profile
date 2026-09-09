"""Supervisor identity matching — refuse substring / wrong checkout / PID reuse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from process_supervisor import (  # noqa: E402
    LaunchIdentity,
    identities_match,
    terminate_pid_tree,
)


def _identity(**overrides) -> LaunchIdentity:
    base = LaunchIdentity(
        pid=4242,
        executable_path=r"c:\python\python.exe",
        command_line=r'c:\python\python.exe c:\profiles\glitch-topstep\scripts\run-topstep-cycle.py',
        argv=(r"c:\python\python.exe", r"c:\profiles\glitch-topstep\scripts\run-topstep-cycle.py"),
        parent_pid=1000,
        started_utc="2026-09-09T12:00:00Z",
        cwd=r"c:\profiles\glitch-topstep\scripts",
        launch_anchor=r"c:\profiles\glitch-topstep\scripts\run-topstep-cycle.py",
    )
    return LaunchIdentity(**{**base.__dict__, **overrides})


class SupervisorIdentityTests(unittest.TestCase):
    def test_matches_exact_topstep_process(self) -> None:
        identity = _identity()
        with mock.patch("process_supervisor.process_is_alive", return_value=True):
            self.assertTrue(
                identities_match(
                    identity,
                    pid=4242,
                    executable_path=r"c:\python\python.exe",
                    command_line=identity.command_line,
                    parent_pid=1000,
                    started_utc="2026-09-09T12:00:00Z",
                    cwd=r"c:\profiles\glitch-topstep\scripts",
                )
            )

    def test_rejects_editor_containing_same_text(self) -> None:
        identity = _identity()
        editor_cmd = (
            r'c:\editors\cursor.exe --goto '
            r'"c:\notes\run-topstep-cycle.py discussion about run-topstep-cycle.py"'
        )
        with mock.patch("process_supervisor.process_is_alive", return_value=True):
            self.assertFalse(
                identities_match(
                    identity,
                    pid=4242,
                    executable_path=r"c:\editors\cursor.exe",
                    command_line=editor_cmd,
                    parent_pid=1000,
                    started_utc="2026-09-09T12:00:00Z",
                )
            )

    def test_rejects_other_checkout_path(self) -> None:
        identity = _identity()
        other = (
            r'c:\python\python.exe '
            r'c:\other\checkout\scripts\run-topstep-cycle.py'
        )
        with mock.patch("process_supervisor.process_is_alive", return_value=True):
            self.assertFalse(
                identities_match(
                    identity,
                    pid=4242,
                    executable_path=r"c:\python\python.exe",
                    command_line=other,
                    parent_pid=1000,
                    started_utc="2026-09-09T12:00:00Z",
                )
            )

    def test_accepts_dead_parent_when_start_matches(self) -> None:
        identity = _identity(parent_pid=1000)

        def alive(pid: int) -> bool:
            return pid == 4242

        with mock.patch("process_supervisor.process_is_alive", side_effect=alive):
            self.assertTrue(
                identities_match(
                    identity,
                    pid=4242,
                    executable_path=identity.executable_path,
                    command_line=identity.command_line,
                    parent_pid=9999,  # reparented / orphaned
                    started_utc="2026-09-09T12:00:00Z",
                )
            )

    def test_rejects_pid_reuse_via_start_skew(self) -> None:
        identity = _identity(started_utc="2026-09-09T12:00:00Z")
        with mock.patch("process_supervisor.process_is_alive", return_value=True):
            self.assertFalse(
                identities_match(
                    identity,
                    pid=4242,
                    executable_path=identity.executable_path,
                    command_line=identity.command_line,
                    parent_pid=1000,
                    started_utc="2026-09-09T15:00:00Z",
                )
            )

    def test_tree_kill_only_when_identity_matches(self) -> None:
        identity = _identity()
        with mock.patch("process_supervisor.sys.platform", "win32"):
            with mock.patch("process_supervisor.process_is_alive", return_value=True):
                with mock.patch("process_supervisor.subprocess.run") as run:
                    killed = terminate_pid_tree(
                        4242,
                        identity=identity,
                        observed_executable=identity.executable_path,
                        observed_command_line=identity.command_line,
                        observed_parent_pid=1000,
                        observed_started_utc="2026-09-09T12:00:00Z",
                    )
                    refused = terminate_pid_tree(
                        4242,
                        identity=identity,
                        observed_executable=r"c:\editors\cursor.exe",
                        observed_command_line="cursor run-topstep-cycle.py notes",
                        observed_parent_pid=1000,
                        observed_started_utc="2026-09-09T12:00:00Z",
                    )
        self.assertTrue(killed)
        self.assertFalse(refused)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args[0][0][:4], ["taskkill", "/F", "/T", "/PID"])


if __name__ == "__main__":
    unittest.main()
