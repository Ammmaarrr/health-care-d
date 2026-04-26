"""Thin OpenAI-compatible LLM client with multi-provider support.

`LLM_PROVIDER` (set in .env) picks one of: openai, databricks, groq,
together, fireworks, openrouter, huggingface, custom. Every provider
exposes the OpenAI Chat Completions wire format, so the public callers
in this file (`chat_json`, `chat_text`, `embed`) do not change.

Embedding fallback: providers that do not serve embeddings (Groq,
Fireworks, OpenRouter, HuggingFace) transparently fall back to OpenAI
embeddings when `EMBED_FALLBACK_TO_OPENAI=true` (default). This keeps
the FAISS index buildable regardless of LLM provider choice.

Token usage is tracked per process so the orchestrator can log a
per-query cost metric to MLflow ("trace cost tracking" hint in the
brief).
"""
from __future__ import annotations

import json
import threading
from typing import Any

from openai import OpenAI

from backend.config import settings


# --------------------------------------------------------------------------- #
# Token usage tracker (read by orchestrator -> MLflow)
# --------------------------------------------------------------------------- #
_usage_lock = threading.Lock()
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}


# Public list-prices ($/1M tokens). Provider-aware. Defaults to 0 when a
# model isn't priced — cost just shows up as $0 rather than crashing.
_PRICE_PER_M_PROMPT_USD: dict[str, float] = {
    # OpenAI
    "gpt-4o-mini": 0.15,
    "gpt-4o": 2.50,
    "gpt-4.1-mini": 0.40,
    "gpt-4.1": 2.00,
    # Databricks Foundation Models (per-DBU; rough USD eq, as of 2025)
    "databricks-meta-llama-3-1-70b-instruct": 1.00,
    "databricks-meta-llama-3-1-405b-instruct": 5.00,
    "databricks-dbrx-instruct": 0.75,
    "databricks-mixtral-8x7b-instruct": 0.50,
    # Groq (free tier reported as $0; using $0.59 community estimate for paid)
    "llama-3.1-70b-versatile": 0.59,
    "llama-3.1-8b-instant": 0.05,
    # Together
    "meta-llama/Llama-3.1-70B-Instruct-Turbo": 0.88,
    "meta-llama/Llama-3.1-8B-Instruct-Turbo": 0.18,
    # Fireworks
    "accounts/fireworks/models/llama-v3p1-70b-instruct": 0.90,
    # OpenRouter (passthrough; varies)
    "openai/gpt-4o-mini": 0.15,
}
_PRICE_PER_M_COMPLETION_USD: dict[str, float] = {
    "gpt-4o-mini": 0.60,
    "gpt-4o": 10.00,
    "gpt-4.1-mini": 1.60,
    "gpt-4.1": 8.00,
    "databricks-meta-llama-3-1-70b-instruct": 3.00,
    "databricks-meta-llama-3-1-405b-instruct": 15.00,
    "databricks-dbrx-instruct": 2.25,
    "databricks-mixtral-8x7b-instruct": 1.00,
    "llama-3.1-70b-versatile": 0.79,
    "llama-3.1-8b-instant": 0.08,
    "meta-llama/Llama-3.1-70B-Instruct-Turbo": 0.88,
    "meta-llama/Llama-3.1-8B-Instruct-Turbo": 0.18,
    "accounts/fireworks/models/llama-v3p1-70b-instruct": 0.90,
    "openai/gpt-4o-mini": 0.60,
}


def reset_token_usage() -> None:
    with _usage_lock:
        _usage["prompt_tokens"] = 0
        _usage["completion_tokens"] = 0
        _usage["calls"] = 0


def get_token_usage() -> dict[str, float]:
    """Snapshot current usage + a rough USD estimate."""
    with _usage_lock:
        snap = dict(_usage)
    model = settings.resolved_llm_model
    p = _PRICE_PER_M_PROMPT_USD.get(model, 0.0) * (snap["prompt_tokens"] / 1_000_000)
    c = _PRICE_PER_M_COMPLETION_USD.get(model, 0.0) * (snap["completion_tokens"] / 1_000_000)
    snap["estimated_cost_usd"] = round(p + c, 6)
    snap["llm_provider"] = settings.llm_provider
    snap["llm_model"] = model
    return snap


def _record_usage(resp: Any) -> None:
    """Add an OpenAI response's usage to the running counters (best-effort)."""
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
    except Exception:
        return
    with _usage_lock:
        _usage["prompt_tokens"] += pt
        _usage["completion_tokens"] += ct
        _usage["calls"] += 1


# --------------------------------------------------------------------------- #
# Client builders (chat client + optional embeddings client)
# --------------------------------------------------------------------------- #
_chat_client: OpenAI | None = None
_embed_client: OpenAI | None = None


def _build_chat_client() -> OpenAI:
    kwargs: dict[str, Any] = {"api_key": settings.resolved_api_key or "missing-key"}
    base = settings.resolved_base_url
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def _build_embed_client() -> OpenAI:
    """Embeddings client. May differ from the chat client when the chat
    provider does not serve embeddings (Groq / Fireworks / OpenRouter /
    HuggingFace). In that case we transparently fall back to OpenAI."""
    if settings.embed_provider == "openai" and settings.llm_provider.lower() != "openai":
        # Use OpenAI explicitly for embeddings, regardless of llm_provider.
        return OpenAI(api_key=settings.openai_api_key or "missing-openai-key")
    return _build_chat_client()


def get_client() -> OpenAI:
    global _chat_client
    if _chat_client is None:
        _chat_client = _build_chat_client()
    return _chat_client


def get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = _build_embed_client()
    return _embed_client


def _supports_json_response_format() -> bool:
    """Some providers / models reject `response_format=json_object`.

    We keep an allow-list of providers known to support it. Everyone
    else just gets a strong system prompt asking for JSON only.
    """
    p = settings.llm_provider.lower()
    return p in {"openai", "databricks", "openrouter", "groq", "together", "fireworks"}


def chat_json(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """Run a chat completion that must return JSON.

    Robust: returns an empty dict on parse failure (e.g. truncated output)
    rather than raising. Callers must handle missing keys gracefully.
    """
    client = get_client()
    create_kwargs: dict[str, Any] = {
        "model": model or settings.resolved_llm_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. No prose."},
            {"role": "user", "content": prompt},
        ],
    }
    if _supports_json_response_format():
        create_kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**create_kwargs)
    except Exception:
        # If the provider rejected `response_format`, retry without it.
        create_kwargs.pop("response_format", None)
        try:
            resp = client.chat.completions.create(**create_kwargs)
        except Exception:
            return {}

    _record_usage(resp)
    content = resp.choices[0].message.content or "{}"
    return _parse_json_loose(content)


def _parse_json_loose(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    cleaned = content.strip().lstrip("```json").lstrip("```").rstrip("```")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for cutoff in range(len(cleaned), 0, -1):
        prefix = cleaned[:cutoff].rstrip().rstrip(",")
        candidate = prefix + "}" if not prefix.endswith("}") else prefix
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def chat_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 400,
) -> str:
    """Plain text completion (used by ranking + trace simplification)."""
    client = get_client()
    try:
        resp = client.chat.completions.create(
            model=model or settings.resolved_llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return ""
    _record_usage(resp)
    return (resp.choices[0].message.content or "").strip()


def embed(texts: list[str], *, model: str | None = None, batch_size: int = 256) -> list[list[float]]:
    """Embed a list of texts. Batches automatically.

    Uses `embed_provider` to decide the actual endpoint, so calling this
    against a non-embedding provider (Groq, Fireworks, OpenRouter,
    HuggingFace) transparently routes to OpenAI when the fallback is on.
    """
    client = get_embed_client()
    out: list[list[float]] = []
    model_name = model or settings.resolved_embed_model
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model_name, input=chunk)
        try:
            usage = getattr(resp, "usage", None)
            if usage is not None:
                pt = int(getattr(usage, "prompt_tokens", 0) or 0)
                with _usage_lock:
                    _usage["prompt_tokens"] += pt
                    _usage["calls"] += 1
        except Exception:
            pass
        out.extend(d.embedding for d in resp.data)
    return out
