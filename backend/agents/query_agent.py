"""Agent 1 — Query Understanding.

Turns a free-text query into a structured `ParsedQuery`.
"""
from __future__ import annotations

import re

from backend.core.llm import chat_json
from backend.core.mlflow_setup import trace_step
from backend.core.prompts import QUERY_PROMPT
from backend.core.schemas import ParsedQuery


_CAPABILITY_HINTS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"\b(appendectomy|operation|operating theatre|ot|surg(?:ery|ical)?)\b", re.I), ("surgery",)),
    (re.compile(r"\b(emergency|casualty|er|ambulance|24/7|24x7)\b", re.I), ("emergency",)),
    (re.compile(r"\b(icu|intensive care|critical care|ventilator)\b", re.I), ("icu",)),
    (re.compile(r"\b(anesthesiologist|anaesthesiologist|anesthesia|anaesthesia)\b", re.I), ("anesthesiologist",)),
    (re.compile(r"\b(oxygen|o2|oxygen supply|oxygen support)\b", re.I), ("oxygen",)),
    (re.compile(r"\b(oncology|cancer|chemotherapy|chemo|radiation therapy|tumou?r)\b", re.I), ("oncology",)),
    (re.compile(r"\b(dialysis|ha?emodialysis|renal|nephrology|kidney failure)\b", re.I), ("dialysis",)),
    (re.compile(r"\b(neonatal|nicu|newborn|premature|paediatric icu|pediatric icu)\b", re.I), ("neonatal",)),
    (re.compile(r"\b(trauma|polytrauma|head injury|road accident|accident ward)\b", re.I), ("trauma",)),
    (re.compile(r"\b(lab|laboratory|pathology|blood test|biochemistry|ha?ematology|microbiology)\b", re.I), ("lab",)),
    (re.compile(r"\b(imaging|x-?ray|mri|ct scan|ct|ultrasound|sonography|radiograph)\b", re.I), ("imaging",)),
)

_PART_TIME_RE = re.compile(r"\b(part[- ]?time|parttime|visiting|on-call)\b", re.I)
_FULL_TIME_RE = re.compile(r"\b(full[- ]?time|resident|in-house)\b", re.I)


def _with_deterministic_hints(query: str, parsed: ParsedQuery) -> ParsedQuery:
    """Patch common medical keywords the LLM may leave as plain constraints."""
    required = list(dict.fromkeys(c.lower() for c in parsed.required_capabilities))
    for pattern, caps in _CAPABILITY_HINTS:
        if pattern.search(query):
            for cap in caps:
                if cap not in required:
                    required.append(cap)

    doctor_preference = parsed.doctor_preference
    if _PART_TIME_RE.search(query):
        doctor_preference = "part-time"
    elif _FULL_TIME_RE.search(query):
        doctor_preference = "full-time"

    return parsed.model_copy(update={
        "required_capabilities": required,
        "doctor_preference": doctor_preference,
    })


@trace_step("query_parse")
def parse_query(query: str) -> ParsedQuery:
    raw = chat_json(QUERY_PROMPT.replace("{query}", query), max_tokens=500)
    parsed = ParsedQuery(**{k: v for k, v in raw.items() if k in ParsedQuery.model_fields})
    return _with_deterministic_hints(query, parsed)
