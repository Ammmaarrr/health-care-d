"""Agent 5 — Validator.

Two-layer validation:
1. Hard rule engine (`core.medical_rules`) — fast, deterministic.
2. LLM cross-check using Tavily-fetched standards — catches subtler issues
   when budget allows.

The hard rules always run. The Tavily layer runs once per *required capability*
in the query, and results are cached by `core.tavily.search`.
"""
from __future__ import annotations

import json
from typing import Iterable

from backend.core import medical_rules
from backend.core.llm import chat_json
from backend.core.mlflow_setup import trace_step
from backend.core.prompts import VALIDATOR_PROMPT
from backend.core.schemas import (
    Capabilities,
    ParsedQuery,
    ValidatorIssue,
    ValidatorResult,
)
from backend.core.tavily import get_standard


def _gather_standards(required: Iterable[str]) -> str:
    parts: list[str] = []
    for cap in required:
        try:
            parts.append(f"### {cap}\n{get_standard(cap)}")
        except Exception as e:  # network/Tavily failure → fall back silently
            parts.append(f"### {cap}\n(no external data: {e})")
    return "\n\n".join(parts)


@trace_step("validator")
def validate(
    cap: Capabilities,
    parsed: ParsedQuery,
    *,
    use_llm: bool = True,
) -> ValidatorResult:
    issues: list[ValidatorIssue] = list(medical_rules.check_contradictions(cap))

    if use_llm and parsed.required_capabilities:
        standards = _gather_standards(parsed.required_capabilities)
        try:
            prompt_text = (
                VALIDATOR_PROMPT
                .replace("{capabilities}", cap.model_dump_json())
                .replace("{standards}", standards[:3000])
            )
            raw = chat_json(prompt_text, max_tokens=500)
            for it in raw.get("issues", []) or []:
                issues.append(
                    ValidatorIssue(
                        capability=str(it.get("capability", "unknown")),
                        issue=str(it.get("issue", "")),
                        severity=it.get("severity", "medium"),
                    )
                )
        except (json.JSONDecodeError, Exception):
            # LLM hiccup → keep rule-based issues only.
            pass

    adjustment = medical_rules.severity_to_adjustment(issues)
    return ValidatorResult(
        valid=not any(i.severity == "high" for i in issues),
        issues=issues,
        confidence_adjustment=adjustment,
    )
