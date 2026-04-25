"""Agent 4 — Reasoning.

Scores hospitals against the parsed query without assuming missing data.
- "yes" capability that matches a requirement = +1.0
- "uncertain" capability for a requirement = +0.3 (some signal but not strong)
- "no" capability for a requirement = -1.0 (disqualifying-ish)
- Rural / location matches handled by retrieval already.

Returns a list of (row, score) sorted by score desc.
"""
from __future__ import annotations

import pandas as pd

from backend.core.schemas import Capabilities, ParsedQuery


_CAP_FIELD_BY_TOKEN = {
    "icu": "has_icu",
    "emergency": "has_emergency",
    "surgery": "has_surgery",
    "anesthesiologist": "has_anesthesiologist",
    "oxygen": "has_oxygen",
}


def score_hospital(cap: Capabilities, parsed: ParsedQuery) -> float:
    if not parsed.required_capabilities:
        return 0.0
    score = 0.0
    for tok in parsed.required_capabilities:
        field = _CAP_FIELD_BY_TOKEN.get(tok.lower())
        if not field:
            continue
        val = getattr(cap, field, "uncertain")
        if val == "yes":
            score += 1.0
        elif val == "uncertain":
            score += 0.3
        elif val == "no":
            score -= 1.0
    # Normalise to 0..1 range relative to maximum possible match.
    max_possible = float(len(parsed.required_capabilities)) or 1.0
    return max(0.0, min(1.0, (score + max_possible) / (2 * max_possible)))


def rank(
    candidates: pd.DataFrame, caps: list[Capabilities], parsed: ParsedQuery
) -> list[tuple[int, float]]:
    """Return [(row_index, score), ...] sorted descending."""
    scored = [(i, score_hospital(caps[i], parsed)) for i in range(len(candidates))]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
