import sys
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ensemble_skill_gate as gate  # noqa: E402


class SpecialtySkillWiringTests(unittest.TestCase):
    def test_canonical_specialty_files_are_substantive_and_distinct(self):
        smart = (ROOT / "skills" / "topstep-smart-money" / "SKILL.md").read_text().lower()
        indicators = (ROOT / "skills" / "topstep-indicators" / "SKILL.md").read_text().lower()
        self.assertNotEqual(smart, indicators)
        self.assertIn("order blocks", smart)
        self.assertIn("liquidity", smart)
        self.assertIn("rsi", indicators)
        self.assertIn("macd", indicators)

    def test_expected_loaded_set_is_exact(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            for skill in ("topstep-smart-money", "topstep-indicators"):
                source = ROOT / "skills" / skill / "SKILL.md"
                target = home / "skills" / skill
                target.mkdir(parents=True)
                target.joinpath("SKILL.md").write_bytes(source.read_bytes())
            result = gate.ensure_skill_files_exist(
                ["topstep-smart-money", "topstep-indicators"],
                profile_root=ROOT,
                hermes_home=home,
            )
            self.assertEqual({row["skill_id"] for row in result["skills"]}, {
                "topstep-smart-money", "topstep-indicators"
            })

    def test_real_hermes_preload_matches_expected_set(self):
        result = gate.require_hermes_preload(
            ["topstep-smart-money", "topstep-indicators"],
            hermes_home=ROOT,
        )
        self.assertEqual(set(result["loaded"]), {
            "topstep-smart-money", "topstep-indicators"
        })
        self.assertEqual(result["missing"], [])
        self.assertTrue(all(
            all(result["specialty_markers"][skill].values())
            for skill in result["specialty_markers"]
        ))

    def test_missing_live_skill_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_hermes_home_missing"):
                gate.ensure_skill_files_exist(
                    ["topstep-smart-money"], profile_root=ROOT, hermes_home=Path(tmp)
                )


if __name__ == "__main__":
    unittest.main()
