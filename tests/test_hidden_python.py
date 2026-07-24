import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import (  # noqa: E402
    hermes_agent_root_from_interpreter,
    merged_subprocess_env,
    windows_hidden_python_invocation,
)


class HiddenPythonTests(unittest.TestCase):
    def test_windows_hidden_python_invocation_bypasses_uv_launcher(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only behavior")

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            venv = base / "hermes-agent" / "venv"
            scripts = venv / "Scripts"
            scripts.mkdir(parents=True)
            site_packages = venv / "Lib" / "site-packages"
            site_packages.mkdir(parents=True)
            (base / "hermes-agent" / "hermes_cli").mkdir(parents=True)
            base_python = base / "uv-python" / "python.exe"
            base_python.parent.mkdir(parents=True)
            base_python.write_text("", encoding="utf-8")
            launcher = scripts / "python.exe"
            launcher.write_text("", encoding="utf-8")
            (venv / "pyvenv.cfg").write_text(
                "\n".join(
                    [
                        f"home = {base_python.parent}",
                        "implementation = CPython",
                        "uv = 0.11.30",
                    ]
                ),
                encoding="utf-8",
            )

            resolved, overlay = windows_hidden_python_invocation(
                str(launcher),
                hermes_agent_root=base / "hermes-agent",
            )

            self.assertEqual(resolved, str(base_python))
            self.assertEqual(overlay["VIRTUAL_ENV"], str(venv))
            self.assertIn(str(base / "hermes-agent"), overlay["PYTHONPATH"])
            self.assertIn(str(site_packages), overlay["PYTHONPATH"])

    def test_merged_subprocess_env_preserves_existing_values(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "existing"}, clear=False):
            env = merged_subprocess_env({"VIRTUAL_ENV": "C:\\venv"})
        self.assertEqual(env["VIRTUAL_ENV"], "C:\\venv")
        self.assertEqual(env["PYTHONPATH"], "existing")

    def test_hermes_agent_root_from_interpreter(self):
        interpreter = Path("C:/hermes/hermes-agent/venv/Scripts/hermes.exe")
        with tempfile.TemporaryDirectory() as root:
            agent_root = Path(root) / "hermes-agent"
            scripts = agent_root / "venv" / "Scripts"
            scripts.mkdir(parents=True)
            (agent_root / "hermes_cli").mkdir()
            resolved = scripts / "hermes.exe"
            resolved.write_text("", encoding="utf-8")
            self.assertEqual(
                hermes_agent_root_from_interpreter(resolved),
                agent_root.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
