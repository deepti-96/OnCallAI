import json
import pathlib
import re
from typing import Any, Dict, List

EXAMPLES_FILE = pathlib.Path(__file__).parent / "data" / "examples.jsonl"


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
                examples.append(json.loads(line))
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
