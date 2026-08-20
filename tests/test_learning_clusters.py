"""Tests for GTHP-021 descriptive similarity clusters."""

from __future__ import annotations

import unittest

from learning_clusters import build_similarity_clusters, summarize_clusters


class LearningClusterTests(unittest.TestCase):
    def test_builds_descriptive_clusters(self) -> None:
        episodes = [
            {
                "intent_id": "a1",
                "action": "ENTER_LONG",
                "rejection_class": "none",
                "pre_decision_state": {"regime": "TREND_UP"},
                "decision_audit": {"final_choice": "ENTER_LONG"},
            },
            {
                "intent_id": "a2",
                "action": "ENTER_LONG",
                "rejection_class": "none",
                "pre_decision_state": {"regime": "TREND_UP"},
                "decision_audit": {"final_choice": "ENTER_LONG"},
            },
            {
                "intent_id": "b1",
                "action": "NOTHING",
                "rejection_class": "participation",
                "pre_decision_state": {"regime": "CHOP"},
                "decision_audit": {"final_choice": "NOTHING"},
            },
        ]
        clusters = build_similarity_clusters(episodes)
        self.assertEqual(clusters[0]["count"], 2)
        self.assertTrue(clusters[0]["descriptive_only"])
        self.assertEqual(len(summarize_clusters(clusters, limit=1)), 1)


if __name__ == "__main__":
    unittest.main()
