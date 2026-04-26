"""Agent 3 — Capability Extraction.

Used both:
- Offline (batch) by `pipeline.batch_extract` over the full dataset.
- Online as a fallback if a candidate row hasn't been pre-extracted yet.

We persist results to `data/extracted/capabilities.parquet` keyed by
`facility_id`, so the runtime path is just a lookup most of the time.
Live-extracted rows are also appended to the cache so subsequent queries
benefit.

Backwards compatible: when the on-disk cache predates a capability
column (e.g. `has_oncology`), `lookup` returns `"uncertain"` for that
field rather than failing.
"""
from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.config import settings
from backend.core.llm import chat_json
from backend.core.mlflow_setup import trace_step
from backend.core.prompts import EXTRACT_PROMPT
from backend.core.schemas import Capabilities, Evidence


_cache_lock = threading.Lock()
_in_memory_cache: dict[str, tuple[Capabilities, Evidence]] = {}


_TRISTATE_VALUES = {"yes", "no", "uncertain"}
_DOCTOR_VALUES = {"full-time", "part-time", "unknown"}


# Capability fields persisted to parquet (keep in sync with `Capabilities`
# in core.schemas). The `_TRISTATE_FIELDS` order is also the column order
# used everywhere (batch_extract, desert.py, lookup).
_TRISTATE_FIELDS: tuple[str, ...] = (
    "has_icu",
    "has_emergency",
    "has_surgery",
    "has_anesthesiologist",
    "has_oxygen",
    "has_oncology",
    "has_dialysis",
    "has_neonatal",
    "has_trauma",
    "has_lab",
    "has_imaging",
)
_EVIDENCE_FIELDS: tuple[str, ...] = (
    "icu",
    "emergency",
    "surgery",
    "anesthesiologist",
    "oxygen",
    "oncology",
    "dialysis",
    "neonatal",
    "trauma",
    "lab",
    "imaging",
    "doctor_type",
)


def _normalize_tristate(v: object) -> str:
    """Coerce any LLM-emitted value to a valid TriState. Default 'uncertain'."""
    if not isinstance(v, str):
        return "uncertain"
    s = v.strip().lower()
    if s in _TRISTATE_VALUES:
        return s
    return "uncertain"


def _normalize_doctor(v: object) -> str:
    if not isinstance(v, str):
        return "unknown"
    s = v.strip().lower()
    if s in _DOCTOR_VALUES:
        return s
    return "unknown"


def _safe_get(row: Any, key: str) -> Any:
    """Pull a value from a pandas Series-ish row. None when missing/NaN."""
    try:
        v = row.get(key) if hasattr(row, "get") else getattr(row, key, None)
    except Exception:
        return None
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
    except Exception:
        pass
    return v


@trace_step("extract_one")
def extract_one(notes: str) -> tuple[Capabilities, Evidence]:
    """Extract capabilities + evidence from a single hospital's notes.

    Robust: never raises. On any LLM/parse failure, returns the all-uncertain
    `Capabilities()` default and empty `Evidence()`.
    """
    if not notes or not notes.strip():
        return Capabilities(), Evidence()

    try:
        raw: dict[str, Any] = chat_json(
            EXTRACT_PROMPT.replace("{notes}", notes[:6000]),
            # Wider capability vocabulary -> larger JSON payload. Keep the
            # ceiling generous so the response is never truncated.
            max_tokens=1400,
        )
    except Exception:
        return Capabilities(), Evidence()

    cap_kwargs: dict[str, str] = {
        f: _normalize_tristate(raw.get(f)) for f in _TRISTATE_FIELDS
    }
    cap_kwargs["doctor_type"] = _normalize_doctor(raw.get("doctor_type"))
    cap = Capabilities(**cap_kwargs)

    evidence_raw = raw.get("evidence") or {}
    if not isinstance(evidence_raw, dict):
        evidence_raw = {}
    ev_kwargs: dict[str, str | None] = {}
    for f in _EVIDENCE_FIELDS:
        val = evidence_raw.get(f)
        ev_kwargs[f] = val if isinstance(val, str) and val.strip() else None
    ev = Evidence(**ev_kwargs)
    return cap, ev


@lru_cache(maxsize=1)
def _load_extractions() -> pd.DataFrame | None:
    if not settings.extractions_path.exists():
        return None
    return pd.read_parquet(settings.extractions_path)


def lookup(facility_id: str) -> tuple[Capabilities, Evidence] | None:
    """Look up a pre-extracted row. Returns None if not yet processed."""
    fid = str(facility_id)
    if fid in _in_memory_cache:
        return _in_memory_cache[fid]
    df = _load_extractions()
    if df is None:
        return None
    row = df[df["facility_id"].astype(str) == fid]
    if row.empty:
        return None
    r = row.iloc[0]

    cap_kwargs: dict[str, str] = {
        f: _normalize_tristate(_safe_get(r, f)) for f in _TRISTATE_FIELDS
    }
    cap_kwargs["doctor_type"] = _normalize_doctor(_safe_get(r, "doctor_type"))
    cap = Capabilities(**cap_kwargs)

    ev_kwargs: dict[str, str | None] = {}
    for f in _EVIDENCE_FIELDS:
        v = _safe_get(r, f"ev_{f}")
        ev_kwargs[f] = v if isinstance(v, str) and v.strip() else None
    ev = Evidence(**ev_kwargs)

    out = (cap, ev)
    _in_memory_cache[fid] = out
    return out


def cache_extraction(facility_id: str, row_meta: dict, cap: Capabilities, ev: Evidence) -> None:
    """Append a freshly-extracted row to the on-disk cache and memory cache.

    Used by the orchestrator after a live (cache-miss) extraction so future
    queries don't pay the LLM cost again.
    """
    fid = str(facility_id)
    _in_memory_cache[fid] = (cap, ev)

    new_row: dict[str, Any] = {
        "facility_id": fid,
        "name": row_meta.get("name"),
        "state": row_meta.get("state"),
        "district": row_meta.get("district"),
        "pin": row_meta.get("pin"),
        "rural": row_meta.get("rural"),
        "facility_type": row_meta.get("facility_type"),
        "doctor_type": cap.doctor_type,
    }
    for f in _TRISTATE_FIELDS:
        new_row[f] = getattr(cap, f)
    for f in _EVIDENCE_FIELDS:
        new_row[f"ev_{f}"] = getattr(ev, f) or ""

    with _cache_lock:
        try:
            existing = (
                pd.read_parquet(settings.extractions_path)
                if settings.extractions_path.exists()
                else pd.DataFrame()
            )
            out = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
            settings.extractions_path.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(settings.extractions_path)
            _load_extractions.cache_clear()
        except Exception:
            pass
