"""Agent 4 — Reasoning.

Scores hospitals against the parsed query without assuming missing data.

Inputs the agent now respects (so the brief's own headline query
"Find the nearest facility in rural Bihar that can perform an emergency
appendectomy and typically leverages part-time doctors" actually works):
- Required capability tristates (yes / uncertain / no).
- `doctor_preference` (full-time / part-time) when supplied.
- Optional Haversine proximity score when the orchestrator passed an
  origin_lat / origin_lng.

Returns a list of (row, score) sorted by score desc.
"""
from __future__ import annotations

import math

import pandas as pd

from backend.core.mlflow_setup import trace_step
from backend.core.schemas import Capabilities, ParsedQuery


# Map every capability token the QueryAgent can emit to the corresponding
# `Capabilities` field. Keep in sync with `core.schemas.CAPABILITY_TOKENS`.
_CAP_FIELD_BY_TOKEN: dict[str, str] = {
    "icu": "has_icu",
    "emergency": "has_emergency",
    "surgery": "has_surgery",
    "anesthesiologist": "has_anesthesiologist",
    "oxygen": "has_oxygen",
    "oncology": "has_oncology",
    "dialysis": "has_dialysis",
    "neonatal": "has_neonatal",
    "trauma": "has_trauma",
    "lab": "has_lab",
    "imaging": "has_imaging",
}


def _capability_match(cap: Capabilities, parsed: ParsedQuery) -> float:
    """Score capability match in [0, 1].

    yes      = +1.0
    uncertain= +0.3   (some signal but not strong)
    no       = -1.0   (disqualifying-ish)
    """
    if not parsed.required_capabilities:
        return 0.5  # no capability ask -> neutral
    score = 0.0
    counted = 0
    for tok in parsed.required_capabilities:
        field = _CAP_FIELD_BY_TOKEN.get(tok.lower())
        if not field:
            continue
        counted += 1
        val = getattr(cap, field, "uncertain")
        if val == "yes":
            score += 1.0
        elif val == "uncertain":
            score += 0.3
        elif val == "no":
            score -= 1.0
    if counted == 0:
        return 0.5
    return max(0.0, min(1.0, (score + counted) / (2 * counted)))


def _doctor_match(cap: Capabilities, parsed: ParsedQuery) -> float | None:
    """Bonus 0..1 if the user expressed a doctor_preference. None = N/A."""
    pref = parsed.doctor_preference
    if not pref:
        return None
    if cap.doctor_type == pref:
        return 1.0
    if cap.doctor_type == "unknown":
        return 0.4  # plausible but unverified
    return 0.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da = math.radians(lat2 - lat1)
    do = math.radians(lng2 - lng1)
    h = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(do / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _proximity_score(distance_km: float | None) -> float | None:
    """Map distance to a 0..1 score (closer = higher). None = N/A."""
    if distance_km is None:
        return None
    if math.isnan(distance_km):
        return None
    # Linear decay 0 km -> 1.0, 500 km -> 0.0, then clamp.
    return max(0.0, min(1.0, 1.0 - distance_km / 500.0))


@trace_step("reasoning_score_hospital")
def score_hospital(
    cap: Capabilities,
    parsed: ParsedQuery,
    *,
    distance_km: float | None = None,
) -> float:
    """Combined match score in [0, 1].

    Weights (chosen so capability remains dominant):
      capability     0.70 (or 1.00 when no other signals)
      doctor pref    0.15  (if user expressed one)
      proximity      0.15  (if origin lat/lng supplied)
    Missing signals collapse their weight back into capability.
    """
    cap_s = _capability_match(cap, parsed)
    doc_s = _doctor_match(cap, parsed)
    prox_s = _proximity_score(distance_km)

    weights = {"cap": 0.70, "doc": 0.15, "prox": 0.15}
    if doc_s is None:
        weights["cap"] += weights.pop("doc")
    if prox_s is None:
        weights["cap"] += weights.pop("prox")

    total = cap_s * weights["cap"]
    if doc_s is not None:
        total += doc_s * weights["doc"]
    if prox_s is not None:
        total += prox_s * weights["prox"]
    return max(0.0, min(1.0, total))


def rank(
    candidates: pd.DataFrame,
    caps: list[Capabilities],
    parsed: ParsedQuery,
    *,
    distances_km: list[float | None] | None = None,
) -> list[tuple[int, float]]:
    """Return [(row_index, score), ...] sorted descending."""
    n = len(candidates)
    distances = distances_km if distances_km is not None else [None] * n
    scored = [(i, score_hospital(caps[i], parsed, distance_km=distances[i])) for i in range(n)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
