"""Pure-regex capability extractor.

Identical pattern set to `databricks/notebooks/02_extract_trust_and_deserts.py`
so the local FastAPI path and the Databricks notebook path agree on a
zero-cost extraction baseline. Used as the default extractor for
non-hospital facility types (dentists, pharmacies, single-doctor
practices) where calling an LLM is wasteful, and as a hybrid fallback
when LLM extraction fails or budget is exhausted.

Conservative by design: returns "uncertain" unless a sentence in the
notes explicitly contains a capability keyword without a negation.
"""
from __future__ import annotations

import re

from backend.core.schemas import Capabilities, Evidence


_YES_PATTERNS: dict[str, re.Pattern[str]] = {
    "has_icu": re.compile(r"\b(icu|intensive\s+care|critical\s+care|ventilator)\b", re.I),
    "has_emergency": re.compile(r"\b(emergency|casualty|er\b|ambulance)\b", re.I),
    "has_surgery": re.compile(
        r"\b(surgery|surgical|operation\s+theatre|\bot\b|appendectomy|"
        r"laparoscopy|c[- ]?section)\b",
        re.I,
    ),
    "has_anesthesiologist": re.compile(
        r"\b(anesthesiologist|anaesthesiologist|anesthesia|anaesthesia)\b", re.I
    ),
    "has_oxygen": re.compile(
        r"\b(oxygen|o2|oxygen\s+concentrator|oxygen\s+supply|oxygen\s+cylinder)\b",
        re.I,
    ),
    "has_oncology": re.compile(
        r"\b(oncology|onco|cancer|chemotherapy|chemo|"
        r"radiation\s+therapy|tumou?r)\b",
        re.I,
    ),
    "has_dialysis": re.compile(
        r"\b(dialysis|haemodialysis|hemodialysis|nephrology|renal)\b", re.I
    ),
    "has_neonatal": re.compile(
        r"\b(neonatal|nicu|newborn|premature|paediatric\s+icu|pediatric\s+icu)\b",
        re.I,
    ),
    "has_trauma": re.compile(
        r"\b(trauma|accident\s+ward|polytrauma|critical\s+injury)\b", re.I
    ),
    "has_lab": re.compile(
        r"\b(laboratory|\blab\b|pathology|microbiology|biochemistry|"
        r"haematology|hematology)\b",
        re.I,
    ),
    "has_imaging": re.compile(
        r"\b(x[\s-]?ray|radiograph|radiology|imaging|ct\s+scan|cat\s+scan|"
        r"mri|ultrasound|sonograph)\b",
        re.I,
    ),
}

_NEGATION = re.compile(
    r"\b(no|not\s+available|without|unavailable|lack(?:s|ing)?|missing|absent)\b",
    re.I,
)
_PART_TIME = re.compile(r"\b(part[\s-]?time|visiting|on[\s-]?call|consultant)\b", re.I)
_FULL_TIME = re.compile(r"\b(full[\s-]?time|resident|in[\s-]?house|on[\s-]?staff)\b", re.I)


def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _sentence_with(pattern: re.Pattern[str], text: str) -> str | None:
    for sentence in _split_sentences(text):
        if pattern.search(sentence):
            return sentence[:500]
    return None


def _tristate(pattern: re.Pattern[str], text: str) -> tuple[str, str | None]:
    """Return (yes/no/uncertain, evidence sentence or None)."""
    evidence = _sentence_with(pattern, text)
    if not evidence:
        return "uncertain", None
    if _NEGATION.search(evidence):
        return "no", evidence
    return "yes", evidence


def _doctor(text: str) -> tuple[str, str | None]:
    if not text:
        return "unknown", None
    pt_match = _PART_TIME.search(text)
    if pt_match:
        return "part-time", _sentence_with(_PART_TIME, text)
    ft_match = _FULL_TIME.search(text)
    if ft_match:
        return "full-time", _sentence_with(_FULL_TIME, text)
    return "unknown", None


def extract_one(notes: str) -> tuple[Capabilities, Evidence]:
    """Pure-regex sibling of `agents.extraction_agent.extract_one`.

    Same return shape as the LLM extractor so callers can be polymorphic.
    """
    text = notes or ""
    cap_kwargs: dict[str, str] = {}
    ev_kwargs: dict[str, str | None] = {}
    for field, pat in _YES_PATTERNS.items():
        state, ev = _tristate(pat, text)
        cap_kwargs[field] = state
        ev_kwargs[field.removeprefix("has_")] = ev
    doc_state, doc_ev = _doctor(text)
    cap_kwargs["doctor_type"] = doc_state
    ev_kwargs["doctor_type"] = doc_ev
    return Capabilities(**cap_kwargs), Evidence(**ev_kwargs)
