"""Hardcoded medical rules — used as ValidatorAgent fallback when Tavily fails.

These are deliberately conservative. They mirror standard hospital licensing
guidance (CGHS / NABH style) without claiming completeness.
"""
from __future__ import annotations

from backend.core.schemas import Capabilities, ValidatorIssue


def check_contradictions(c: Capabilities) -> list[ValidatorIssue]:
    """Return a list of issues found purely from rule logic."""
    issues: list[ValidatorIssue] = []

    # Surgery without anesthesiologist is a hard fail.
    if c.has_surgery == "yes" and c.has_anesthesiologist != "yes":
        issues.append(
            ValidatorIssue(
                capability="surgery",
                issue=(
                    "Surgery is claimed but anesthesiologist is "
                    f"'{c.has_anesthesiologist}'. Surgery requires anesthesia coverage."
                ),
                severity="high",
            )
        )

    # Surgery requires oxygen too.
    if c.has_surgery == "yes" and c.has_oxygen == "no":
        issues.append(
            ValidatorIssue(
                capability="surgery",
                issue="Surgery claimed without oxygen supply on record.",
                severity="high",
            )
        )

    # Emergency without oxygen is suspicious.
    if c.has_emergency == "yes" and c.has_oxygen != "yes":
        issues.append(
            ValidatorIssue(
                capability="emergency",
                issue=(
                    "Emergency care is claimed but oxygen is "
                    f"'{c.has_oxygen}'. Emergency care requires reliable oxygen."
                ),
                severity="medium" if c.has_oxygen == "uncertain" else "high",
            )
        )

    # ICU without explicit critical-care signals is weak.
    if c.has_icu == "yes" and c.has_oxygen != "yes":
        issues.append(
            ValidatorIssue(
                capability="icu",
                issue="ICU claimed but oxygen support not confirmed.",
                severity="medium",
            )
        )

    return issues


def severity_to_adjustment(issues: list[ValidatorIssue]) -> float:
    """Map validator issues to a confidence adjustment in [-0.5, 0]."""
    weight = {"low": 0.05, "medium": 0.15, "high": 0.30}
    total = sum(weight[i.severity] for i in issues)
    return max(-0.5, -total)
