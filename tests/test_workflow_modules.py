import unittest
from pathlib import Path

from workflows.delivery_recovery import classify_delivery_result, classify_gateway_rejection
from workflows.intent_outbox import intent_is_entry, pending_outbox


ROOT = Path(__file__).resolve().parents[1]


class WorkflowModuleTests(unittest.TestCase):
    def test_workflow_modules_exist(self) -> None:
        required = [
            "scripts/workflows/delivery_recovery.py",
            "scripts/workflows/intent_outbox.py",
            "scripts/workflows/gateway_session.py",
            "scripts/workflows/decision_journal.py",
            "scripts/workflows/cognition_prompt.py",
            "scripts/workflows/wake_triggers.py",
        ]
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_classify_delivery_result_transport_uncertain(self) -> None:
        self.assertEqual(
            classify_delivery_result({"transport_error": "timeout"}),
            "transport_uncertain",
        )

    def test_classify_gateway_rejection_none_on_success(self) -> None:
        self.assertIsNone(classify_gateway_rejection({"http_status": 200, "body": {}}))

    def test_intent_is_entry(self) -> None:
        self.assertTrue(intent_is_entry({"action": "ENTER_LONG"}))
        self.assertFalse(intent_is_entry({"action": "HOLD"}))

    def test_pending_outbox_empty_when_missing(self) -> None:
        self.assertIsNone(pending_outbox(ROOT / "tests" / "fixtures" / "missing-state"))


if __name__ == "__main__":
    unittest.main()
