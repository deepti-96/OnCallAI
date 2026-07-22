import importlib
import tempfile
import unittest
from pathlib import Path


class ServiceRegistryTestCase(unittest.TestCase):
    def setUp(self):
        from app.models import service_registry

        self.registry = importlib.reload(service_registry)

    def tearDown(self):
        self.registry.load_service_catalog.cache_clear()

    def test_normalize_service_name_collapses_noise(self):
        self.assertEqual(self.registry.normalize_service_name("  Payments Service! "), "payments-service")
        self.assertEqual(self.registry.normalize_service_name("checkout_api"), "checkout-api")

    def test_resolve_service_name_uses_aliases(self):
        self.assertEqual(self.registry.resolve_service_name("payments-service"), "payment-service")
        self.assertEqual(self.registry.resolve_service_name("stock-service"), "inventory-service")

    def test_get_service_enrichment_applies_environment_overrides(self):
        enrichment = self.registry.get_service_enrichment("payment-service", "staging")

        self.assertEqual(enrichment["service"], "payment-service")
        self.assertEqual(enrichment["requested_service"], "payment-service")
        self.assertEqual(enrichment["resolved_service"], "payment-service")
        self.assertIn("payments-service", enrichment["aliases"])
        self.assertEqual(
            enrichment["dashboard_url"],
            "https://grafana.example/d/payment-service-staging",
        )
        self.assertEqual(
            enrichment["recent_deploy_hint"],
            "Validate staging deploys before promoting to prod.",
        )

    def test_invalid_service_catalog_json_raises_value_error(self):
        temp_dir = tempfile.TemporaryDirectory()
        original_catalog = self.registry.CATALOG_FILE
        try:
            invalid_catalog = Path(temp_dir.name) / "service_catalog.json"
            invalid_catalog.write_text("{not-json", encoding="utf-8")
            self.registry.CATALOG_FILE = invalid_catalog
            self.registry.load_service_catalog.cache_clear()

            with self.assertRaises(ValueError):
                self.registry.load_service_catalog()
        finally:
            self.registry.CATALOG_FILE = original_catalog
            self.registry.load_service_catalog.cache_clear()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
