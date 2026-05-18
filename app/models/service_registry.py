import json
import pathlib
from functools import lru_cache
from typing import Any, Dict

CATALOG_FILE = pathlib.Path(__file__).with_name("service_catalog.json")


@lru_cache(maxsize=1)
def load_service_catalog() -> Dict[str, Dict[str, Any]]:
    if not CATALOG_FILE.exists():
        return {}
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def get_service_enrichment(service: str, environment: str | None = None) -> Dict[str, Any]:
    catalog = load_service_catalog()
    service_entry = catalog.get(service, {})
    enrichment = dict(service_entry)
    if service_entry:
        enrichment["service"] = service
        if environment:
            enrichment["environment"] = environment
    return enrichment
