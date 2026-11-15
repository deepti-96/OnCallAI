"""Thin client for the MIND Developer REST API.

Only endpoints used by the official @astramindapp/mcp-server package
(v0.32.1, dist/mind-client.js) are called here. Each MCP tool in that
package is a wrapper over one of these routes:

  mind_query                 -> POST /developer/v1/query
  mind_remember action=create (type=entry) -> POST /developer/v1/entries
  mind_remember action=search (type=entry) -> GET  /developer/v1/entries/search
  mind_remember action=delete (type=entry) -> DELETE /developer/v1/entries/{id}
  mind_graph   (stats)       -> GET  /developer/v1/graph

Auth is an X-API-Key header carrying a key that starts with "mind_".
We use the REST routes instead of speaking MCP because OnCallAI is a
Python worker, not an LLM agent. Same backend, same graph.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class MindError(Exception):
    """Base class for MIND failures."""


class MindUnavailable(MindError):
    """Network error, timeout, 5xx, auth failure or rate limit. Caller should fall back."""


class MindResponseError(MindError):
    """MIND answered but the body was not what the documented schema promises."""


class MindClient:
    def __init__(self, api_key: str, base_url: str = "https://www.m-i-n-d.ai", timeout: float = 4.0):
        if not api_key:
            raise ValueError("MIND api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --- transport -------------------------------------------------------
    def _request(self, method: str, path: str, body: Dict[str, Any] | None = None,
                 params: Dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                text = res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise MindUnavailable(f"MIND HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MindUnavailable(f"MIND unreachable: {exc}") from exc
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise MindResponseError(f"MIND returned non-JSON: {text[:200]}") from exc

    # --- documented operations -------------------------------------------
    def query(self, query: str, *, mode: str = "hybrid", retrieve_only: bool = True,
              max_context_tokens: int | None = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"query": query, "mode": mode, "retrieve_only": retrieve_only}
        if max_context_tokens:
            body["max_context_tokens"] = max_context_tokens
        result = self._request("POST", "/developer/v1/query", body)
        if not isinstance(result, dict) or not isinstance(result.get("response", ""), str):
            raise MindResponseError("query response missing 'response' string")
        return result

    def create_entry(self, *, title: str, content: str, tags: List[str] | None = None,
                     folder: str | None = None, supersedes: List[str] | None = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"title": title, "content": content}
        if tags:
            body["tags"] = tags
        if folder:
            body["folder"] = folder
        if supersedes:
            body["supersedes"] = supersedes
        result = self._request("POST", "/developer/v1/entries", body)
        if not isinstance(result, dict):
            raise MindResponseError("create_entry response was not an object")
        return result

    def search_entries(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        result = self._request("GET", "/developer/v1/entries/search",
                               params={"query": query, "limit": str(limit)})
        if not isinstance(result, dict) or not isinstance(result.get("entries", []), list):
            raise MindResponseError("search_entries response missing 'entries' list")
        return result.get("entries", [])

    def delete_entry(self, entry_id: str) -> None:
        self._request("DELETE", f"/developer/v1/entries/{urllib.parse.quote(entry_id)}")

    def graph_info(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "/developer/v1/graph")
