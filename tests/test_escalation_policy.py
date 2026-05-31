import datetime
import unittest

from app.models.escalation_policy import compute_escalation_guidance


class EscalationPolicyTestCase(unittest.TestCase):
    def test_critical_tier_one_incident_pages_primary_contact(self):
        incident = {
            "severity": "CRITICAL",
            "created_at": "2026-05-31T10:00:00Z",
            "payload": {
                "occurrence_count": 2,
                "enrichment": {
                    "primary_contact": "payments-oncall",
                    "owner_team": "payments-platform",
                    "escalation_policy": "page-payments-primary",
                    "service_tier": "tier-1",
                },
            },
        }

        guidance = compute_escalation_guidance(incident)

        self.assertEqual(guidance["priority"], "Immediate")
        self.assertTrue(guidance["should_page"])
        self.assertEqual(guidance["target"], "payments-oncall")
        self.assertIn("critical severity", guidance["reason"])

    def test_repeated_medium_incident_gets_elevated_priority(self):
        now_iso = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        incident = {
            "severity": "MEDIUM",
            "created_at": now_iso,
            "payload": {
                "occurrence_count": 4,
                "enrichment": {
                    "owner_team": "inventory-core",
                    "primary_contact": "inventory-oncall",
                    "escalation_policy": "page-inventory-primary",
                    "service_tier": "tier-2",
                },
            },
        }

        guidance = compute_escalation_guidance(incident)

        self.assertEqual(guidance["priority"], "Elevated")
        self.assertFalse(guidance["should_page"])
        self.assertIn("4 repeated alerts", guidance["reason"])
        self.assertIn("Notify inventory-core", guidance["action"])


if __name__ == "__main__":
    unittest.main()
