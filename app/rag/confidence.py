from __future__ import annotations

from typing import Any, Iterable


def _clamp_confidence(value: float) -> float:
    return round(max(0.1, min(value, 0.95)), 2)


def calibrate_confidence(
    *,
    rule_matched: bool,
    retrieved_examples: Iterable[dict[str, Any]] = (),
    evidence_count: int = 0,
    log_count: int = 0,
) -> float:
    examples = list(retrieved_examples)
    score = 0.22

    if rule_matched:
        score += 0.34
    elif examples:
        score += 0.18

    if evidence_count:
        score += min(0.12, 0.03 * min(evidence_count, 4))

    if log_count:
        score += min(0.08, 0.02 * min(log_count, 4))

    if examples:
        score += min(0.16, sum(float(example.get("confidence_hint", 0.0)) for example in examples[:3]) * 0.08)
        score += min(0.06, 0.02 * max(len(examples) - 1, 0))

    return _clamp_confidence(score)
