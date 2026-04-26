"""Hardcoded medical rules — used as ValidatorAgent fallback when Tavily fails.

These are deliberately conservative. They mirror standard hospital licensing
guidance (CGHS / NABH style) without claiming completeness.

Severity grading distinguishes:
- HIGH: claimed capability + explicitly missing prerequisite ('no').
- MEDIUM: claimed capability + unconfirmed prerequisite ('uncertain').
- LOW: weaker signal of the same.
"""
from __future__ import annotations

from backend.core.schemas import Capabilities, ValidatorIssue


def _sev(missing_value: str, *, high: str = "high", uncertain: str = "medium") -> str:
    """Map the prerequisite's value to a severity label."""
    if missing_value == "no":
        return high
    if missing_value == "uncertain":
        return uncertain
    return "low"


def check_contradictions(c: Capabilities) -> list[ValidatorIssue]:
    """Return a list of issues found purely from rule logic.

    Covers the MVP capabilities (ICU/emergency/surgery/anesthesia/oxygen)
    AND the high-acuity specialties the brief calls out (Oncology,
    Dialysis, Neonatal, Trauma).
    """
    issues: list[ValidatorIssue] = []

    if c.has_surgery == "yes" and c.has_anesthesiologist != "yes":
        issues.append(ValidatorIssue(
            capability="surgery",
            issue=(
                f"Surgery is claimed but anesthesiologist is "
                f"'{c.has_anesthesiologist}'. Surgery requires anesthesia coverage."
            ),
            severity=_sev(c.has_anesthesiologist),
        ))

    if c.has_surgery == "yes" and c.has_oxygen != "yes":
        issues.append(ValidatorIssue(
            capability="surgery",
            issue=f"Surgery claimed but oxygen is '{c.has_oxygen}'.",
            severity=_sev(c.has_oxygen, high="high", uncertain="low"),
        ))

    if c.has_emergency == "yes" and c.has_oxygen != "yes":
        issues.append(ValidatorIssue(
            capability="emergency",
            issue=(
                f"Emergency care is claimed but oxygen is "
                f"'{c.has_oxygen}'. Emergency care requires reliable oxygen."
            ),
            severity=_sev(c.has_oxygen),
        ))

    if c.has_icu == "yes" and c.has_oxygen != "yes":
        issues.append(ValidatorIssue(
            capability="icu",
            issue=f"ICU claimed but oxygen support is '{c.has_oxygen}'.",
            severity=_sev(c.has_oxygen, high="high", uncertain="low"),
        ))

    # --- High-acuity specialties --------------------------------------- #
    if c.has_oncology == "yes" and c.has_lab != "yes":
        issues.append(ValidatorIssue(
            capability="oncology",
            issue=f"Oncology claimed but laboratory is '{c.has_lab}'.",
            severity=_sev(c.has_lab, high="medium", uncertain="medium"),
        ))

    if c.has_oncology == "yes" and c.has_imaging != "yes":
        issues.append(ValidatorIssue(
            capability="oncology",
            issue=f"Oncology claimed but imaging support is '{c.has_imaging}'.",
            severity=_sev(c.has_imaging, high="medium", uncertain="medium"),
        ))

    if c.has_dialysis == "yes" and c.has_lab != "yes":
        issues.append(ValidatorIssue(
            capability="dialysis",
            issue=f"Dialysis claimed but laboratory is '{c.has_lab}'.",
            severity=_sev(c.has_lab, high="medium", uncertain="low"),
        ))

    if c.has_neonatal == "yes" and c.has_oxygen != "yes":
        issues.append(ValidatorIssue(
            capability="neonatal",
            issue=f"Neonatal/NICU claimed but oxygen is '{c.has_oxygen}'.",
            severity=_sev(c.has_oxygen),
        ))

    if c.has_trauma == "yes" and c.has_emergency != "yes":
        issues.append(ValidatorIssue(
            capability="trauma",
            issue=(
                f"Trauma care claimed but emergency capability is "
                f"'{c.has_emergency}'."
            ),
            severity=_sev(c.has_emergency),
        ))

    return issues


def severity_to_adjustment(issues: list[ValidatorIssue]) -> float:
    """Map validator issues to a confidence adjustment.

    Range: [-0.35, 0]. Even multiple high-severity issues bottom out
    at -0.35 so a partially-validated facility never goes to a score
    of literal zero from validation alone.
    """
    weight = {"low": 0.03, "medium": 0.10, "high": 0.20}
    total = sum(weight[i.severity] for i in issues)
    return max(-0.35, -total)
