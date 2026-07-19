import importlib
import unittest


class RagScoringTestCase(unittest.TestCase):
    def setUp(self):
        from app.rag import confidence, loader

        self.confidence = importlib.reload(confidence)
        self.loader = importlib.reload(loader)

    def test_retrieve_examples_prioritizes_stronger_matches(self):
        corpus = (
            "Payment service saw ECONNREFUSED after database connection refused errors, "
            "and the logs also mentioned a NullPointerException stack trace."
        )

        examples = self.loader.retrieve_examples(corpus, limit=2)

        self.assertGreaterEqual(len(examples), 2)
        self.assertEqual(examples[0]["root_cause"], "DB pod crashed / not ready")
        self.assertGreater(examples[0]["retrieval_score"], examples[1]["retrieval_score"])
        self.assertNotIn("_text_tokens", examples[0])
        self.assertNotIn("_pattern_tokens", examples[0])

    def test_calibrate_confidence_rewards_supported_analysis(self):
        supported = self.confidence.calibrate_confidence(
            rule_matched=True,
            retrieved_examples=[{"confidence_hint": 0.82}, {"confidence_hint": 0.73}],
            evidence_count=3,
            log_count=3,
        )
        weak = self.confidence.calibrate_confidence(
            rule_matched=False,
            retrieved_examples=[],
            evidence_count=1,
            log_count=1,
        )

        self.assertGreater(supported, weak)
        self.assertGreaterEqual(supported, 0.8)
        self.assertLess(weak, 0.6)


if __name__ == "__main__":
    unittest.main()
