import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ensemble_skill_gate as gate  # noqa: E402
from distribution_manifest import file_sha256, iter_sha256sums_entries  # noqa: E402


class SpecialtySkillWiringTests(unittest.TestCase):
    def test_specialty_front_matter_is_valid_utf8(self):
        for skill in ("topstep-smart-money", "topstep-indicators"):
            metadata = gate.parse_skill_front_matter(ROOT / "skills" / skill / "SKILL.md", expected_skill_id=skill)
            self.assertEqual(metadata["name"], skill)
            self.assertTrue(metadata["description"])

    def test_discovery_is_deterministic(self):
        first = gate.discover_skill_files(ROOT)
        second = gate.discover_skill_files(ROOT)
        self.assertEqual(first, sorted(first))
        self.assertEqual(first, second)
        self.assertIn("topstep-smart-money", first)
        self.assertIn("topstep-indicators", first)

    def test_skill_manifest_checksums_match(self):
        manifest = {path: digest for digest, path in iter_sha256sums_entries(ROOT)}
        for skill in ("topstep-smart-money", "topstep-indicators"):
            path = f"skills/{skill}/SKILL.md"
            self.assertIn(path, manifest)
            self.assertEqual(manifest[path], file_sha256(ROOT / path))

    def test_invalid_front_matter_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text("# invalid\n", encoding="utf-8")
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_front_matter_invalid"):
                gate.parse_skill_front_matter(path, expected_skill_id="topstep-smart-money")

    def test_utf8_and_path_with_spaces_are_supported(self):
        with tempfile.TemporaryDirectory(prefix="hermes skill ") as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text("---\nname: topstep-smart-money\ndescription: evidência UTF-8\n---\n", encoding="utf-8")
            metadata = gate.parse_skill_front_matter(path, expected_skill_id="topstep-smart-money")
            self.assertEqual(metadata["description"], "evidência UTF-8")
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
        try:
            result = gate.require_hermes_preload(
                ["topstep-smart-money", "topstep-indicators"],
                hermes_home=ROOT,
            )
        except gate.SkillPreloadError as exc:
            if str(exc) == "hermes_skill_api_unavailable:ModuleNotFoundError":
                self.skipTest("Hermes agent package is not installed in this CI runner")
            raise
        self.assertEqual(set(result["loaded"]), {
            "topstep-smart-money", "topstep-indicators"
        })
        self.assertEqual(result["missing"], [])
        self.assertTrue(all(
            all(result["specialty_markers"][skill].values())
            for skill in result["specialty_markers"]
        ))

    def test_real_hermes_preload_is_stable_under_repeated_parallel_calls(self):
        expected = {"topstep-smart-money", "topstep-indicators"}

        def load_once():
            return gate.require_hermes_preload(list(expected), hermes_home=ROOT)

        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _index: load_once(), range(8)))
        except gate.SkillPreloadError as exc:
            if str(exc) == "hermes_skill_api_unavailable:ModuleNotFoundError":
                self.skipTest("Hermes agent package is not installed in this CI runner")
            raise
        self.assertEqual({tuple(sorted(result["loaded"])) for result in results}, {
            tuple(sorted(expected))
        })
        self.assertTrue(all(not result["missing"] for result in results))

    def test_missing_live_skill_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_hermes_home_missing"):
                gate.ensure_skill_files_exist(
                    ["topstep-smart-money"], profile_root=ROOT, hermes_home=Path(tmp)
                )


if __name__ == "__main__":
    unittest.main()
