"""Agent 1 — Query Understanding.

Turns a free-text query into a structured `ParsedQuery`.
"""
from __future__ import annotations

from backend.core.llm import chat_json
from backend.core.prompts import QUERY_PROMPT
from backend.core.schemas import ParsedQuery


def parse_query(query: str) -> ParsedQuery:
    raw = chat_json(QUERY_PROMPT.replace("{query}", query), max_tokens=400)
    # Pydantic ignores unknown keys, fills defaults for missing ones.
    return ParsedQuery(**{k: v for k, v in raw.items() if k in ParsedQuery.model_fields})
