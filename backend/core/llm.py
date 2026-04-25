"""Thin OpenAI-compatible LLM client. Provider-agnostic by design."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from backend.config import settings


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _client = OpenAI(**kwargs)
    return _client


def chat_json(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """Run a chat completion that must return JSON.

    We force `response_format=json_object` so the model returns parseable
    JSON. Caller is responsible for shape validation (Pydantic).
    """
    client = get_client()
    resp = client.chat.completions.create(
        model=model or settings.openai_llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Return only valid JSON. No prose."},
            {"role": "user", "content": prompt},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Last-resort: strip code fences if model added them.
        cleaned = content.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(cleaned)


def chat_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 400,
) -> str:
    """Plain text completion (used by ranking + trace simplification)."""
    client = get_client()
    resp = client.chat.completions.create(
        model=model or settings.openai_llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()


def embed(texts: list[str], *, model: str | None = None, batch_size: int = 256) -> list[list[float]]:
    """Embed a list of texts. Batches automatically."""
    client = get_client()
    out: list[list[float]] = []
    model_name = model or settings.openai_embed_model
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model_name, input=chunk)
        out.extend(d.embedding for d in resp.data)
    return out
