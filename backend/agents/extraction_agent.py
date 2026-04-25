"""Agent 3 — Capability Extraction.

Used both:
- Offline (batch) by `pipeline.batch_extract` over the full dataset.
- Online as a fallback if a candidate row hasn't been pre-extracted yet.

We persist results to `data/extracted/capabilities.parquet` keyed by
`facility_id`, so the runtime path is just a lookup most of the time.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from backend.config import settings
from backend.core.llm import chat_json
from backend.core.prompts import EXTRACT_PROMPT
from backend.core.schemas import Capabilities, Evidence


def extract_one(notes: str) -> tuple[Capabilities, Evidence]:
    """Extract capabilities + evidence from a single hospital's notes."""
    if not notes or not notes.strip():
        return Capabilities(), Evidence()

    raw: dict[str, Any] = chat_json(
        EXTRACT_PROMPT.format(notes=notes[:6000]),  # safety truncate
        max_tokens=600,
    )
    cap_fields = {k: raw.get(k) for k in Capabilities.model_fields if raw.get(k) is not None}
    cap = Capabilities(**cap_fields)
    evidence_raw = raw.get("evidence") or {}
    ev = Evidence(**{k: evidence_raw.get(k) for k in Evidence.model_fields})
    return cap, ev


@lru_cache(maxsize=1)
def _load_extractions() -> pd.DataFrame | None:
    if not settings.extractions_path.exists():
        return None
    return pd.read_parquet(settings.extractions_path)


def lookup(facility_id: str) -> tuple[Capabilities, Evidence] | None:
    """Look up a pre-extracted row. Returns None if not yet processed."""
    df = _load_extractions()
    if df is None:
        return None
    row = df[df["facility_id"].astype(str) == str(facility_id)]
    if row.empty:
        return None
    r = row.iloc[0]
    cap = Capabilities(
        has_icu=r.get("has_icu", "uncertain"),
        has_emergency=r.get("has_emergency", "uncertain"),
        has_surgery=r.get("has_surgery", "uncertain"),
        has_anesthesiologist=r.get("has_anesthesiologist", "uncertain"),
        has_oxygen=r.get("has_oxygen", "uncertain"),
        doctor_type=r.get("doctor_type", "unknown"),
    )
    ev = Evidence(
        icu=r.get("ev_icu") or None,
        emergency=r.get("ev_emergency") or None,
        surgery=r.get("ev_surgery") or None,
        anesthesiologist=r.get("ev_anesthesiologist") or None,
        oxygen=r.get("ev_oxygen") or None,
        doctor_type=r.get("ev_doctor_type") or None,
    )
    return cap, ev
