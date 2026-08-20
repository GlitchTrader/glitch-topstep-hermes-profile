"""Hermetic profile root guard for tests and CI."""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from common import profile_root, state_root


class HermeticProfileTests(unittest.TestCase):
    def test_profile_root_respects_hermes_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HERMES_HOME"] = tmp
            root = profile_root()
            self.assertEqual(root, Path(tmp).resolve())
            self.assertEqual(state_root(root), root / "state")

    def test_profile_root_without_hermes_home_is_under_user_home(self) -> None:
        env = os.environ.copy()
        env.pop("HERMES_HOME", None)
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            root = profile_root()
            self.assertIn("hermes", str(root).lower())


if __name__ == "__main__":
    unittest.main()
