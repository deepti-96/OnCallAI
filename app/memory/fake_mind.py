"""In-memory stand-in for MIND, for tests and the offline demo.

THIS IS NOT MIND. It mimics the documented response shapes of the REST
routes in mind_client.py, and imitates two retrieval styles so the demo
can show the difference in mechanics:

  mode="naive"  -> token overlap over entry text (a stand-in for vector similarity)
  other modes   -> 1-hop walk over an entity graph built from the records
                   (service, dependencies, affected component)

Real MIND uses LightRAG extraction and embeddings. Run
scripts/mind_experiment.py --live to see how the real thing behaves.
"""
from __future__ import annotations

import itertools
import json
import re
from typing import Any, Dict, List

from app.memory.mind_client import MindResponseError, MindUnavailable

TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RECORD_RE = re.compile(r"OnCallAI-Record:\s*(\{.*\})")
STOP = {"the", "a", "an", "and", "or", "of", "on", "in", "to", "for", "with", "was", "is", "it",
        "find", "past", "oncallai", "incidents", "incident", "involving", "list", "each", "its",
        "root", "cause", "mitigation", "like", "failures", "around", "from", "by", "after", "not"}


def _tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall((text or "").lower()) if t not in STOP and len(t) > 2}


class FakeMind:
    def __init__(self, *, fail_with: Exception | None = None, malformed: bool = False,
                 corrupt_records: bool = False):
        self.entries: Dict[str, Dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self.fail_with = fail_with
        self.malformed = malformed
        self.corrupt_records = corrupt_records
        self.calls: List[str] = []

    # --- failure injection ---------------------------------------------
    def _maybe_fail(self):
        if self.fail_with is not None:
            raise self.fail_with

    # --- MindClient-compatible surface ---------------------------------
    def create_entry(self, *, title, content, tags=None, folder=None, supersedes=None):
        self.calls.append("create_entry")
        self._maybe_fail()
        eid = f"entry_{next(self._ids)}"
        self.entries[eid] = {"entry_id": eid, "title": title, "content": content, "tags": tags or []}
        return {"entry_id": eid, "title": title}

    def search_entries(self, query, limit=15):
        self.calls.append("search_entries")
        self._maybe_fail()
        hits = [e for e in self.entries.values() if query.lower() in (e["title"] + e["content"]).lower()]
        return hits[:limit]

    def delete_entry(self, entry_id):
        self.calls.append("delete_entry")
        self.entries.pop(entry_id, None)

    def graph_info(self):
        return {"entries": len(self.entries), "simulated": True}

    def query(self, query, *, mode="hybrid", retrieve_only=True, max_context_tokens=None):
        self.calls.append(f"query:{mode}")
        self._maybe_fail()
        if self.malformed:
            return {"unexpected": "shape"}  # caught by the real client's schema check below
        hits = self._naive(query) if mode == "naive" else self._graph(query)
        if mode == "mix":
            hits = list(dict.fromkeys(hits + self._naive(query)))
        body = "\n\n---\n\n".join(self.entries[h]["content"] for h in hits)
        if self.corrupt_records:
            body = body.replace('"root_cause"', '"root_cause"\x00BROKEN', 1).replace("}", "", 1) + \
                "\nOnCallAI-Record: {not json}\n"
        return {"response": body, "sources": [self.entries[h]["title"] for h in hits],
                "model_used": "fake", "credits_used": 0, "credits_remaining": 0}

    # --- retrieval styles ----------------------------------------------
    def _naive(self, query: str, threshold: float = 0.12) -> List[str]:
        q = _tokens(query)
        scored = []
        for eid, e in self.entries.items():
            text = e["content"].split("OnCallAI-Incident-Key")[0]
            t = _tokens(text)
            overlap = len(q & t) / max(len(q | t), 1)
            if overlap >= threshold:
                scored.append((overlap, eid))
        return [eid for _, eid in sorted(scored, reverse=True)[:3]]

    def _record(self, eid: str) -> Dict[str, Any]:
        m = RECORD_RE.search(self.entries[eid]["content"])
        try:
            return json.loads(m.group(1)) if m else {}
        except json.JSONDecodeError:
            return {}

    def _graph(self, query: str) -> List[str]:
        edges: Dict[str, set[str]] = {}
        nodes_of: Dict[str, set[str]] = {}
        for eid in self.entries:
            rec = self._record(eid)
            nodes = {n for n in [rec.get("service"), rec.get("affected_component"), *rec.get("dependencies", [])] if n}
            nodes_of[eid] = nodes
            svc = rec.get("service")
            for n in nodes - {svc}:
                if svc:
                    edges.setdefault(svc, set()).add(n)
                    edges.setdefault(n, set()).add(svc)
        q = query.lower()
        seeds = {n for n in edges if re.search(rf"\b{re.escape(n)}\b", q)}
        expanded = set(seeds)
        for s in seeds:  # one hop through relationships
            expanded |= edges.get(s, set())
        return [eid for eid, nodes in nodes_of.items() if nodes & expanded]


class StrictFakeMind(FakeMind):
    """FakeMind behind the real client's response validation, for malformed-response tests."""

    def query(self, *args, **kwargs):
        result = super().query(*args, **kwargs)
        if not isinstance(result, dict) or not isinstance(result.get("response"), str):
            raise MindResponseError("query response missing 'response' string")
        return result


__all__ = ["FakeMind", "StrictFakeMind", "MindUnavailable", "MindResponseError"]
