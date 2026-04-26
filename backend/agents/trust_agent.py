"""Agent 6 — Trust Scoring.

Composite 0..1 score from four factors:

  trust = clip(0, 1, completeness * 0.30
                    + consistency  * 0.25
                    + validator    * 0.30
                    + evidence     * 0.15
                    + validator_adjustment)

The capability vocabulary now includes the high-acuity specialties the
brief calls out (oncology, dialysis, neonatal, trauma) plus supporting
infrastructure (lab, imaging) so the trust score reflects the same
breadth of evidence that the rest of the system extracts.
"""
from __future__ import annotations

from backend.core.mlflow_setup import trace_step
from backend.core.schemas import (
    Capabilities,
    Evidence,
    TrustBreakdown,
    TrustResult,
    ValidatorResult,
)


# Keep this list in sync with `extraction_agent._TRISTATE_FIELDS` + doctor_type.
_CAP_FIELDS: tuple[str, ...] = (
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
    "doctor_type",
)
_EV_FIELDS: tuple[str, ...] = (
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


def _completeness(cap: Capabilities) -> float:
    """Fraction of fields that are not 'uncertain'/'unknown'."""
    known = 0
    for f in _CAP_FIELDS:
        v = getattr(cap, f)
        if v not in ("uncertain", "unknown"):
            known += 1
    return known / len(_CAP_FIELDS)


def _consistency(cap: Capabilities) -> float:
    """1.0 minus penalty for known internal contradictions."""
    score = 1.0
    if cap.has_surgery == "yes" and cap.has_anesthesiologist != "yes":
        score -= 0.4
    if cap.has_emergency == "yes" and cap.has_oxygen == "no":
        score -= 0.3
    if cap.has_icu == "yes" and cap.has_oxygen != "yes":
        score -= 0.2
    if cap.has_oncology == "yes" and (cap.has_lab != "yes" or cap.has_imaging != "yes"):
        score -= 0.2
    if cap.has_dialysis == "yes" and cap.has_lab != "yes":
        score -= 0.15
    if cap.has_neonatal == "yes" and cap.has_oxygen != "yes":
        score -= 0.2
    if cap.has_trauma == "yes" and cap.has_emergency != "yes":
        score -= 0.15
    return max(0.0, score)


def _evidence_strength(ev: Evidence) -> float:
    """Fraction of evidence fields that have a non-empty supporting snippet."""
    filled = sum(1 for f in _EV_FIELDS if getattr(ev, f))
    return filled / len(_EV_FIELDS)


def _validator_score(v: ValidatorResult) -> float:
    if not v.issues:
        return 1.0
    high = sum(1 for i in v.issues if i.severity == "high")
    med = sum(1 for i in v.issues if i.severity == "medium")
    low = sum(1 for i in v.issues if i.severity == "low")
    return max(0.0, 1.0 - (high * 0.4 + med * 0.2 + low * 0.05))


@trace_step("trust_score")
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
