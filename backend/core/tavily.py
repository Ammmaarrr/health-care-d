"""Tavily wrapper with on-disk cache.

We hit Tavily once per *capability standard* (e.g. "ICU requirements") and
cache the result. Standards do not change between hackathon hours.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from tavily import TavilyClient

from backend.config import settings


_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


def _cache_path(query: str) -> Path:
    settings.tavily_cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
    return settings.tavily_cache_dir / f"{h}.json"


def search(query: str, *, max_results: int = 5, ttl_seconds: int = 86_400) -> dict[str, Any]:
    """Cached Tavily search. Returns the raw Tavily response dict.

    Cache TTL defaults to 24h.
    """
    path = _cache_path(query)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - cached.get("_cached_at", 0) < ttl_seconds:
            return cached["data"]

    client = _get_client()
    data = client.search(
        query=query,
        search_depth="basic",
        max_results=max_results,
        include_answer=True,
    )
    path.write_text(
        json.dumps({"_cached_at": time.time(), "query": query, "data": data}, indent=2),
        encoding="utf-8",
    )
    return data


def get_standard(capability: str) -> str:
    """Get a short text blurb describing minimum requirements for a capability."""
    queries = {
        "icu": "ICU intensive care unit minimum requirements equipment staff hospital",
        "emergency": "hospital emergency department minimum requirements oxygen staff",
        "surgery": "hospital operating theatre surgery minimum requirements anesthesiologist equipment",
        "anesthesiologist": "anesthesiologist role hospital surgery requirement",
        "oxygen": "hospital oxygen supply requirements emergency surgery",
    }
    q = queries.get(capability.lower(), f"{capability} hospital requirements")
    res = search(q)
    answer = res.get("answer") or ""
    snippets = "\n".join(r.get("content", "") for r in res.get("results", [])[:3])
    return (answer + "\n\n" + snippets).strip()[:1500]
