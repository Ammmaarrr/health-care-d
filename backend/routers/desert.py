"""GET /desert-map route — aggregates pre-extracted capabilities by state."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import pandas as pd

from backend.config import settings
from backend.core.schemas import DesertGap, DesertMapResponse


router = APIRouter()

_CAP_COLS = ("has_icu", "has_emergency", "has_surgery",
             "has_anesthesiologist", "has_oxygen")


@router.get("/desert-map", response_model=DesertMapResponse)
def desert_map(
    min_total: int = Query(5, ge=0, description="Hide groups with fewer than this many facilities."),
    capability: str | None = Query(None, description="Optional filter: 'icu', 'surgery', etc."),
) -> DesertMapResponse:
    """Aggregated view of capability gaps by state.

    A `gap_ratio` close to 1 means most facilities in that state either
    explicitly lack or have unconfirmed access to the capability.
    """
    if not settings.extractions_path.exists():
        raise HTTPException(503, "Extractions not built yet.")
    df = pd.read_parquet(settings.extractions_path)
    if "state" not in df.columns:
        raise HTTPException(500, "Extractions missing `state` column.")

    gaps: list[DesertGap] = []
    for state, sub in df.groupby("state"):
        total = int(len(sub))
        if total < min_total:
            continue
        for col in _CAP_COLS:
            if col not in sub.columns:
                continue
            cap_name = col.replace("has_", "")
            if capability and cap_name != capability.lower():
                continue
            missing = int(((sub[col] == "no") | (sub[col] == "uncertain")).sum())
            gaps.append(
                DesertGap(
                    state=str(state),
                    capability=cap_name,
                    missing_or_uncertain=missing,
                    total=total,
                    gap_ratio=round(missing / total, 3),
                )
            )
    # Sort: worst gaps (highest ratio) first.
    gaps.sort(key=lambda g: g.gap_ratio, reverse=True)
    return DesertMapResponse(gaps=gaps)
