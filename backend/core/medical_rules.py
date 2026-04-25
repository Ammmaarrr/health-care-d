"""Hardcoded medical rules — used as ValidatorAgent fallback when Tavily fails.

These are deliberately conservative. They mirror standard hospital licensing
guidance (CGHS / NABH style) without claiming completeness.
"""
from __future__ import annotations

from backend.core.schemas import Capabilities, ValidatorIssue


def check_contradictions(c: Capabilities) -> list[ValidatorIssue]:
    """Return a list of issues found purely from rule logic.

    Severity grading distinguishes:
    - HIGH: a claimed capability + an *explicitly missing* prerequisite.
            (Hospital says "yes" to surgery and "no" to anesthesiologist.)
    - MEDIUM: a claimed capability + an *unconfirmed* prerequisite.
              (Hospital says "yes" to surgery and "uncertain" on anesthesiologist.)
    - LOW: weaker signal of the same.

    This way "uncertain" data doesn't crater the trust score the same way
    explicit contradictions do.
    """
    issues: list[ValidatorIssue] = []

    # Surgery requires anesthesiologist.
    if c.has_surgery == "yes" and c.has_anesthesiologist != "yes":
        sev = "high" if c.has_anesthesiologist == "no" else "medium"
        issues.append(
            ValidatorIssue(
                capability="surgery",
                issue=(
                    f"Surgery is claimed but anesthesiologist is "
                    f"'{c.has_anesthesiologist}'. Surgery requires anesthesia coverage."
                ),
                severity=sev,
            )
        )

    # Surgery requires oxygen.
    if c.has_surgery == "yes" and c.has_oxygen != "yes":
        sev = "high" if c.has_oxygen == "no" else "low"
        issues.append(
            ValidatorIssue(
                capability="surgery",
                issue=f"Surgery claimed but oxygen is '{c.has_oxygen}'.",
                severity=sev,
            )
        )

    # Emergency care requires oxygen.
    if c.has_emergency == "yes" and c.has_oxygen != "yes":
        sev = "high" if c.has_oxygen == "no" else "medium"
        issues.append(
            ValidatorIssue(
                capability="emergency",
                issue=(
                    f"Emergency care is claimed but oxygen is "
                    f"'{c.has_oxygen}'. Emergency care requires reliable oxygen."
                ),
                severity=sev,
            )
        )

    # ICU without oxygen signals is weak.
    if c.has_icu == "yes" and c.has_oxygen != "yes":
        sev = "high" if c.has_oxygen == "no" else "low"
        issues.append(
            ValidatorIssue(
                capability="icu",
                issue=f"ICU claimed but oxygen support is '{c.has_oxygen}'.",
                severity=sev,
            )
        )

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
