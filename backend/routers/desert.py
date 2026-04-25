"""GET /desert-map route — aggregates pre-extracted capabilities by state."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
import pandas as pd

from backend.config import settings
from backend.core.schemas import DesertGap, DesertMapResponse


router = APIRouter()

_CAP_COLS = ("has_icu", "has_emergency", "has_surgery",
             "has_anesthesiologist", "has_oxygen")


@router.get("/desert-map", response_model=DesertMapResponse)
def desert_map() -> DesertMapResponse:
    if not settings.extractions_path.exists():
        raise HTTPException(503, "Extractions not built yet.")
    df = pd.read_parquet(settings.extractions_path)
    if "state" not in df.columns:
        raise HTTPException(500, "Extractions missing `state` column.")

    gaps: list[DesertGap] = []
    for state, sub in df.groupby("state"):
        total = int(len(sub))
        for cap in _CAP_COLS:
            if cap not in sub.columns:
                continue
            missing = int(((sub[cap] == "no") | (sub[cap] == "uncertain")).sum())
            gaps.append(
                DesertGap(
                    state=str(state),
                    capability=cap.replace("has_", ""),
                    missing_or_uncertain=missing,
                    total=total,
                )
            )
    # Sort: worst gaps (highest ratio) first.
    gaps.sort(key=lambda g: g.missing_or_uncertain / max(g.total, 1), reverse=True)
    return DesertMapResponse(gaps=gaps)
