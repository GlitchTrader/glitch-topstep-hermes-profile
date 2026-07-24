import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("launch_topstep_cycle", SCRIPTS / "launch-topstep-cycle.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LaunchCycleTests(unittest.TestCase):
    def test_launch_skips_when_lock_is_active(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            state = root / "state"
            state.mkdir(parents=True)
            lock = state / "direct-cycle.lock"
            lock.write_text("1", encoding="utf-8")
            with mock.patch.object(MODULE, "configure_environment", return_value=root):
                with mock.patch.object(MODULE.subprocess, "Popen") as popen:
                    with mock.patch.object(sys, "argv", ["launch-topstep-cycle.py"]):
                        code = MODULE.main()
            self.assertEqual(code, 0)
            popen.assert_not_called()

    def test_launch_spawns_worker_when_unlocked(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            (root / "state" / "supervisor").mkdir(parents=True)
            with mock.patch.object(MODULE, "configure_environment", return_value=root):
                with mock.patch.object(MODULE.subprocess, "Popen", return_value=mock.Mock(pid=42)) as popen:
                    with mock.patch.object(sys, "argv", ["launch-topstep-cycle.py"]):
                        code = MODULE.main()
            self.assertEqual(code, 0)
            popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
