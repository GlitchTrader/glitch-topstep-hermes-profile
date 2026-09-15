import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ensemble_skill_gate as gate  # noqa: E402


SKILL = ROOT / "skills" / "adversarial-risk" / "SKILL.md"


class AdversarialRiskSkillTests(unittest.TestCase):
    def test_registry_discovers_explicit_profile_skill(self):
        registry = json.loads((ROOT / "evaluation" / "registry.json").read_text(encoding="utf-8"))
        matrix = json.loads((ROOT / "evaluation" / "capability-matrix.json").read_text(encoding="utf-8"))
        profile = next(row for row in registry["profiles"] if row["profile_id"] == "adversarial-risk")
        self.assertEqual(profile["skills"], ["adversarial-risk"])
        self.assertEqual(matrix["profiles"]["adversarial-risk"]["skills"], ["adversarial-risk"])
        self.assertIn("adversarial-risk", gate.discover_skill_files(ROOT))

    def test_front_matter_and_utf8_are_valid(self):
        metadata = gate.parse_skill_front_matter(SKILL, expected_skill_id="adversarial-risk")
        self.assertEqual(metadata["name"], "adversarial-risk")
        self.assertTrue(metadata["description"])
        self.assertIn("evidência", SKILL.read_text(encoding="utf-8"))

    def test_structured_objection_output_declares_required_fields(self):
        text = SKILL.read_text(encoding="utf-8")
        required = {
            "severity", "risk_code", "evidence", "evidence_refs",
            "objective_rule_match", "eliminates_candidate", "uncertainties",
            "envelope_identity", "objections",
        }
        self.assertTrue(required.issubset(set(text.split('"'))))

    def _installation(self):
        tmp = tempfile.TemporaryDirectory()
        profile = Path(tmp.name) / "profile"
        home = Path(tmp.name) / "home"
        (profile / "skills" / "adversarial-risk").mkdir(parents=True)
        (home / "skills" / "adversarial-risk").mkdir(parents=True)
        shutil.copyfile(SKILL, profile / "skills" / "adversarial-risk" / "SKILL.md")
        shutil.copyfile(SKILL, home / "skills" / "adversarial-risk" / "SKILL.md")
        return tmp, profile, home

    def test_missing_skill_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_profile_missing"):
                gate.validate_skill_installation(
                    ["adversarial-risk"], profile_root=Path(tmp), hermes_home=Path(tmp) / "home"
                )

    def test_hash_drift_fails_closed(self):
        tmp, profile, home = self._installation()
        try:
            path = home / "skills" / "adversarial-risk" / "SKILL.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_hash_mismatch:adversarial-risk"):
                gate.validate_skill_installation(["adversarial-risk"], profile_root=profile, hermes_home=home)
        finally:
            tmp.cleanup()

    def test_front_matter_name_drift_fails_closed(self):
        tmp, profile, home = self._installation()
        try:
            path = home / "skills" / "adversarial-risk" / "SKILL.md"
            path.write_text(path.read_text(encoding="utf-8").replace("name: adversarial-risk", "name: wrong-name"), encoding="utf-8")
            with self.assertRaisesRegex(gate.SkillPreloadError, "skill_front_matter_invalid:adversarial-risk:name"):
                gate.validate_skill_installation(["adversarial-risk"], profile_root=profile, hermes_home=home)
        finally:
            tmp.cleanup()

    def test_drift_check_accepts_matching_front_matter_and_hash(self):
        tmp, profile, home = self._installation()
        try:
            result = gate.validate_skill_installation(["adversarial-risk"], profile_root=profile, hermes_home=home)
            self.assertEqual(result["skills"][0]["skill_id"], "adversarial-risk")
            self.assertEqual(result["skills"][0]["profile_path"], str(profile / "skills" / "adversarial-risk" / "SKILL.md"))
        finally:
            tmp.cleanup()

    def test_discovery_order_is_deterministic(self):
        first = gate.discover_skill_files(ROOT)
        self.assertEqual(first, sorted(first))
        self.assertEqual(first, gate.discover_skill_files(ROOT))


if __name__ == "__main__":
    unittest.main()
