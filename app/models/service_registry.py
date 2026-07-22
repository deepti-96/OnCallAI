import json
import pathlib
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, Tuple

CATALOG_FILE = pathlib.Path(__file__).with_name("service_catalog.json")
SERVICE_NAME_RE = re.compile(r"[^a-z0-9]+")


def normalize_service_name(service: str) -> str:
    text = str(service or "").strip().lower()
    if not text:
        return ""
    normalized = SERVICE_NAME_RE.sub("-", text).strip("-")
    return re.sub(r"-+", "-", normalized)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def validate_service_catalog(catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(catalog, dict):
        raise ValueError("Service catalog must be a JSON object")

    validated: Dict[str, Dict[str, Any]] = {}
    for raw_name, entry in catalog.items():
        service_name = normalize_service_name(raw_name)
        if not service_name:
            raise ValueError("Service catalog contains an empty service name")
        if not isinstance(entry, dict):
            raise ValueError(f"Service catalog entry for {raw_name!r} must be an object")

        aliases = []
        for alias in _as_list(entry.get("aliases")):
            aliases.append(normalize_service_name(alias))
        environments = entry.get("environments") or {}
        if not isinstance(environments, dict):
            raise ValueError(f"Service catalog entry for {raw_name!r} has invalid environments metadata")
        for environment_name, environment_entry in environments.items():
            if not isinstance(environment_entry, dict):
                raise ValueError(
                    f"Service catalog entry for {raw_name!r} has invalid metadata for environment {environment_name!r}"
                )

        validated[service_name] = {
            **entry,
            "service": service_name,
            "aliases": sorted({alias for alias in aliases if alias and alias != service_name}),
            "environments": environments,
        }

    return validated


@lru_cache(maxsize=1)
def load_service_catalog() -> Dict[str, Dict[str, Any]]:
    if not CATALOG_FILE.exists():
        return {}

    try:
        raw_catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid service catalog JSON: {exc}") from exc

    return validate_service_catalog(raw_catalog)


def _iter_service_entries(catalog: Dict[str, Dict[str, Any]]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    return catalog.items()


def resolve_service_name(service: str) -> str:
    requested = normalize_service_name(service)
    if not requested:
        return ""

    catalog = load_service_catalog()
    if requested in catalog:
        return requested

    for canonical_name, entry in _iter_service_entries(catalog):
        aliases = entry.get("aliases") or []
        if requested in aliases:
            return canonical_name

    return requested


def get_service_enrichment(
    service: str,
    environment: str | None = None,
    *,
    requested_service: str | None = None,
) -> Dict[str, Any]:
    catalog = load_service_catalog()
    canonical_service = resolve_service_name(service)
    service_entry = catalog.get(canonical_service, {})
    enrichment = dict(service_entry)

    requested_service = normalize_service_name(requested_service or service)
    environment_overrides = service_entry.get("environments", {}) if isinstance(service_entry, dict) else {}
    if environment and environment_overrides:
        environment_entry = environment_overrides.get(environment) or environment_overrides.get(environment.lower())
        if isinstance(environment_entry, dict):
            enrichment.update(environment_entry)

    if service_entry:
        enrichment["service"] = canonical_service
        enrichment["requested_service"] = requested_service
        enrichment["resolved_service"] = canonical_service
        enrichment["aliases"] = service_entry.get("aliases", [])
        if environment:
            enrichment["environment"] = environment
    return enrichment
