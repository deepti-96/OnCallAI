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


def _example_score(corpus_tokens: set[str], corpus: str, example: Dict[str, Any]) -> Dict[str, Any] | None:
    pattern = example.get("pattern", "")
    regex_hits = len(re.findall(pattern, corpus, flags=re.I)) if pattern else 0
    overlap = len(corpus_tokens & set(example.get("_text_tokens", set())))
    pattern_overlap = len(corpus_tokens & set(example.get("_pattern_tokens", set())))

    if regex_hits == 0 and overlap == 0 and pattern_overlap == 0:
        return None

    retrieval_score = round(
        (regex_hits * 2.0)
        + (pattern_overlap * 0.45)
        + (overlap * 0.25),
        3,
    )
    confidence_hint = min(0.95, round(0.35 + (retrieval_score / 8.0), 2))
    public_example = {key: value for key, value in example.items() if not key.startswith("_")}
    return {
        **public_example,
        "match_count": max(regex_hits, overlap, pattern_overlap),
        "token_overlap": overlap,
        "pattern_overlap": pattern_overlap,
        "retrieval_score": retrieval_score,
        "confidence_hint": confidence_hint,
    }


def retrieve_examples(corpus: str, limit: int = 2) -> List[Dict[str, Any]]:
    corpus_tokens = _tokenize(corpus)
    matches: List[Dict[str, Any]] = []
    for example in load_examples():
        scored = _example_score(corpus_tokens, corpus, example)
        if scored is not None:
            matches.append(scored)

    matches.sort(
        key=lambda item: (
            item["retrieval_score"],
            item["confidence_hint"],
            item["match_count"],
        ),
        reverse=True,
    )
    return matches[:limit]
