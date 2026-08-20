import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AuditRegressionMatrixTests(unittest.TestCase):
    def test_regression_files_exist(self) -> None:
        required = [
            "tests/test_state_store.py",
            "tests/test_jsonl_tail.py",
            "tests/test_paired_contract.py",
            "tests/test_workflow_modules.py",
            "scripts/check_profile_quality.py",
            "scripts/workflows/delivery_recovery.py",
        ]
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
