"""Agent 7 — Trace.

Builds a structured `Trace` object plus an LLM-rendered prose explanation
per hospital. Cheap: one short LLM call.
"""
from __future__ import annotations

import json
from typing import Any

from backend.core.llm import chat_text
from backend.core.prompts import RANK_PROMPT, TRACE_PROMPT
from backend.core.schemas import (
    Capabilities,
    ParsedQuery,
    Trace,
    ValidatorResult,
)


def explain_hospital(
    name: str,
    location: dict[str, Any],
    cap: Capabilities,
    validator: ValidatorResult,
    parsed: ParsedQuery,
) -> str:
    return chat_text(
        RANK_PROMPT.format(
            parsed_query=parsed.model_dump_json(),
            name=name,
            location=json.dumps(location, default=str),
            capabilities=cap.model_dump_json(),
            flags=[i.issue for i in validator.issues],
        ),
        temperature=0.2,
        max_tokens=80,
    )


def simplify_trace(trace: Trace) -> str:
    return chat_text(
        TRACE_PROMPT.format(trace_json=trace.model_dump_json()),
        temperature=0.2,
        max_tokens=300,
    )
