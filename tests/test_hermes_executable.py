"""Tests for host Hermes executable resolution."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hermes_executable import resolve_hermes_executable


class ResolveHermesExecutableTests(unittest.TestCase):
    def test_uses_configured_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes = Path(tmp) / "hermes.exe"
            hermes.write_text("", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"HERMES_EXECUTABLE": str(hermes), "LOCALAPPDATA": tmp},
                clear=False,
            ):
                with mock.patch("hermes_executable.shutil.which", return_value=None):
                    self.assertEqual(resolve_hermes_executable(), str(hermes.resolve()))

    def test_falls_back_to_localappdata_install_when_path_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes = (
                Path(tmp)
                / "hermes"
                / "hermes-agent"
                / "venv"
                / "Scripts"
                / "hermes.exe"
            )
            hermes.parent.mkdir(parents=True)
            hermes.write_text("", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"LOCALAPPDATA": tmp, "HERMES_EXECUTABLE": ""},
                clear=False,
            ):
                with mock.patch("hermes_executable.shutil.which", return_value=None):
                    self.assertEqual(resolve_hermes_executable(), str(hermes.resolve()))

    def test_raises_when_no_candidate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {"LOCALAPPDATA": tmp, "HERMES_EXECUTABLE": ""},
                clear=False,
            ):
                with mock.patch("hermes_executable.shutil.which", return_value=None):
                    with self.assertRaisesRegex(RuntimeError, "hermes_executable_not_found"):
                        resolve_hermes_executable()


if __name__ == "__main__":
    unittest.main()
