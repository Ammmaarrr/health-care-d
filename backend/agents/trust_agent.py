"""Agent 6 — Trust Scoring.

Composite 0..1 score from four factors:

  trust = clip(0, 1, completeness * 0.30
                    + consistency  * 0.25
                    + validator    * 0.30
                    + evidence     * 0.15
                    + validator_adjustment)
"""
from __future__ import annotations

from backend.core.schemas import (
    Capabilities,
    Evidence,
    TrustBreakdown,
    TrustResult,
    ValidatorResult,
)


def _completeness(cap: Capabilities) -> float:
    """Fraction of fields that are not 'uncertain'/'unknown'."""
    fields = ("has_icu", "has_emergency", "has_surgery",
              "has_anesthesiologist", "has_oxygen", "doctor_type")
    known = 0
    for f in fields:
        v = getattr(cap, f)
        if v not in ("uncertain", "unknown"):
            known += 1
    return known / len(fields)


def _consistency(cap: Capabilities) -> float:
    """1.0 minus penalty for known internal contradictions."""
    score = 1.0
    if cap.has_surgery == "yes" and cap.has_anesthesiologist != "yes":
        score -= 0.4
    if cap.has_emergency == "yes" and cap.has_oxygen == "no":
        score -= 0.3
    if cap.has_icu == "yes" and cap.has_oxygen != "yes":
        score -= 0.2
    return max(0.0, score)


def _evidence_strength(ev: Evidence) -> float:
    """Fraction of evidence fields that have a non-empty supporting snippet."""
    fields = ("icu", "emergency", "surgery", "anesthesiologist", "oxygen", "doctor_type")
    filled = sum(1 for f in fields if getattr(ev, f))
    return filled / len(fields)


def _validator_score(v: ValidatorResult) -> float:
    if not v.issues:
        return 1.0
    high = sum(1 for i in v.issues if i.severity == "high")
    med = sum(1 for i in v.issues if i.severity == "medium")
    low = sum(1 for i in v.issues if i.severity == "low")
    return max(0.0, 1.0 - (high * 0.4 + med * 0.2 + low * 0.05))


def score(
    cap: Capabilities,
    ev: Evidence,
    validator: ValidatorResult,
) -> TrustResult:
    breakdown = TrustBreakdown(
        completeness=_completeness(cap),
        consistency=_consistency(cap),
        validator=_validator_score(validator),
        evidence_strength=_evidence_strength(ev),
    )
    raw = (
        breakdown.completeness * 0.30
        + breakdown.consistency * 0.25
        + breakdown.validator * 0.30
        + breakdown.evidence_strength * 0.15
        + validator.confidence_adjustment  # negative or zero
    )
    final = max(0.0, min(1.0, raw))

    flags = [i.issue for i in validator.issues]
    if breakdown.completeness < 0.4:
        flags.append("Sparse data - many fields uncertain.")

    return TrustResult(trust_score=round(final, 3), flags=flags, breakdown=breakdown)
