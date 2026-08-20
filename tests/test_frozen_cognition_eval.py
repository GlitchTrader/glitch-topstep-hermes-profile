import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "frozen_corpus"
sys.path.insert(0, str(SCRIPTS))

EVAL_SPEC = importlib.util.spec_from_file_location(
    "frozen_eval", SCRIPTS / "evaluate-frozen-cognition.py"
)
EVAL = importlib.util.module_from_spec(EVAL_SPEC)
assert EVAL_SPEC and EVAL_SPEC.loader
EVAL_SPEC.loader.exec_module(EVAL)

RUN_SPEC = importlib.util.spec_from_file_location(
    "run_frozen_cognition", SCRIPTS / "run-frozen-cognition.py"
)
RUN = importlib.util.module_from_spec(RUN_SPEC)
assert RUN_SPEC and RUN_SPEC.loader
RUN_SPEC.loader.exec_module(RUN)


class FrozenCognitionEvalTests(unittest.TestCase):
    def test_reports_action_rejection_and_abstention_diffs_without_promotion(self):
        baseline = {
            "schema_version": "glitch.topstep.cognition_run.v1",
            "prompt_version": "v9", "corpus_hash": "abc",
            "decisions": [{"frame_id": "1", "action": "NOTHING", "rejection": None,
                           "abstention_classification": "missed"}],
        }
        candidate = {
            "schema_version": "glitch.topstep.cognition_run.v1",
            "prompt_version": "v10", "corpus_hash": "abc",
            "decisions": [{"frame_id": "1", "action": "ENTER_LONG", "rejection": "range",
                           "abstention_classification": None}],
        }
        report = EVAL.compare_runs(baseline, candidate)
        self.assertEqual(report["changed_frames"], 1)
        self.assertFalse(report["armed_promotion_allowed"])
        self.assertEqual(
            report["diffs"][0]["changed_fields"],
            ["action", "rejection", "abstention_classification"],
        )

    def test_rejects_non_identical_corpus(self):
        left = {"prompt_version": "a", "corpus_hash": "1", "decisions": []}
        right = {"prompt_version": "b", "corpus_hash": "2", "decisions": []}
        with self.assertRaisesRegex(ValueError, "frozen_corpus_hash_mismatch"):
            EVAL.compare_runs(left, right)

    def test_builds_runs_from_frozen_corpus_and_diffs_prompt_versions(self):
        baseline = RUN.build_run(
            frames_dir=FIXTURES / "minute-frames",
            state_root=FIXTURES / "baseline-state",
            prompt_version="glitch-topstep-v9",
        )
        candidate = RUN.build_run(
            frames_dir=FIXTURES / "minute-frames",
            state_root=FIXTURES / "candidate-state",
            prompt_version="glitch-topstep-v10",
        )
        self.assertEqual(baseline["corpus_hash"], candidate["corpus_hash"])
        report = EVAL.compare_runs(baseline, candidate)
        self.assertEqual(report["frames_compared"], 2)
        self.assertEqual(report["changed_frames"], 1)
        self.assertFalse(report["armed_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
