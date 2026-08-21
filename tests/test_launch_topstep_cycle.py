import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "launch_topstep_cycle",
    SCRIPTS / "launch-topstep-cycle.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LaunchTopstepCycleTests(unittest.TestCase):
    def test_skips_launch_when_model_owner_active(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            args = mock.Mock(
                profile="glitch-topstep",
                timeout_seconds=240,
                packet_rollover_wait_seconds=5,
                dry_run=False,
            )
            with mock.patch.object(MODULE, "configure_environment", return_value=root_path), mock.patch.object(
                MODULE,
                "active_model_owner",
                return_value={
                    "owner_kind": "direct_cycle",
                    "pid": 4242,
                },
            ), mock.patch.object(MODULE.subprocess, "Popen") as popen:
                result = MODULE.launch(args)

            self.assertFalse(result["launched"])
            self.assertEqual(result["reason"], "direct_cycle_already_running")
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
