import json
import pathlib
import re
from functools import lru_cache
from typing import Any, Dict, List

EXAMPLES_FILE = pathlib.Path(__file__).parent / "data" / "examples.jsonl"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "")}


def _normalize_example(example: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(example)
    normalized.setdefault("pattern", "")
    normalized.setdefault("root_cause", "")
    normalized.setdefault("mitigation", [])
    if not isinstance(normalized["mitigation"], list):
        normalized["mitigation"] = [str(normalized["mitigation"])]
    normalized["_pattern_tokens"] = _tokenize(str(normalized.get("pattern", "")))
    normalized["_text_tokens"] = _tokenize(
        " ".join(
            str(value)
            for value in (
                normalized.get("pattern", ""),
                normalized.get("root_cause", ""),
                " ".join(str(item) for item in normalized.get("mitigation", [])),
            )
            if value
        )
    )
    return normalized


@lru_cache(maxsize=1)
def load_examples() -> List[Dict[str, Any]]:
    if not EXAMPLES_FILE.exists():
        return []

    examples: List[Dict[str, Any]] = []
    with EXAMPLES_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(_normalize_example(json.loads(line)))
            except json.JSONDecodeError:
                continue
    return examples


def retrieve_examples(corpus: str, limit: int = 2) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for example in load_examples():
        pattern = example.get("pattern")
        if not pattern:
            continue
        hit_count = len(re.findall(pattern, corpus, flags=re.I))
        if hit_count:
            matches.append(
                {
                    **example,
                    "match_count": hit_count,
                }
            )

    matches.sort(key=lambda item: item["match_count"], reverse=True)
    return matches[:limit]
