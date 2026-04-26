"""GET /desert-map route — aggregates pre-extracted capabilities by state."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import pandas as pd

from backend.config import settings
from backend.core.schemas import (
    DesertGap,
    DesertMapResponse,
    PinDesertGap,
    PinDesertMapResponse,
)


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


@router.get("/desert-map/pins", response_model=PinDesertMapResponse)
def desert_map_pins(
    min_per_pin: int = Query(1, ge=1, description="Hide PINs with fewer than this many facilities."),
    capability: str = Query("icu", description="Capability: icu, emergency, surgery, anesthesiologist, oxygen"),
    top: int = Query(40, ge=1, le=200, description="Return up to this many highest-risk PINs."),
) -> PinDesertMapResponse:
    """PIN-level medical desert / crisis zones for dynamic mapping.

    Joins extraction capabilities with processed lat/lng + PIN. `risk` is the
    fraction of facilities in that PIN that are `no` or `uncertain` on the axis.
    """
    if not settings.extractions_path.exists():
        raise HTTPException(503, "Extractions not built yet.")
    if not settings.processed_path.exists():
        raise HTTPException(503, "Processed hospitals not built yet.")

    ex = pd.read_parquet(settings.extractions_path)
    pr = pd.read_parquet(settings.processed_path)
    cap = capability.lower()
    if not cap.startswith("has_"):
        cap = f"has_{cap}"
    key = cap
    if key not in ex.columns:
        raise HTTPException(400, f"Unknown capability / column: {key}")

    merged = ex.merge(
        pr[["facility_id", "pin", "latitude", "longitude", "state"]],
        on="facility_id",
        how="left",
    )
    merged["pin"] = merged["pin"].fillna("").astype(str).str.strip()
    merged = merged[merged["pin"].str.len() > 0]

    cap_label = key.replace("has_", "", 1) if key.startswith("has_") else key
    zones: list[PinDesertGap] = []
    for pin, sub in merged.groupby("pin"):
        pin_s = str(pin).strip()
        if not pin_s:
            continue
        n = int(len(sub))
        if n < min_per_pin:
            continue
        miss = int(((sub[key] == "no") | (sub[key] == "uncertain")).sum())
        risk = round(miss / n, 3) if n else 0.0
        st_series = sub["state"].dropna()
        stv: str | None
        if len(st_series):
            s0 = st_series.iloc[0]
            stv = None if s0 is None or (isinstance(s0, float) and pd.isna(s0)) else str(s0)
        else:
            stv = None
        lat = sub["latitude"].dropna()
        lng = sub["longitude"].dropna()
        c_lat = float(lat.mean()) if len(lat) else None
        c_lng = float(lng.mean()) if len(lng) else None
        zones.append(
            PinDesertGap(
                pin=pin_s,
                state=stv,
                capability=cap_label,
                total=n,
                missing_or_uncertain=miss,
                risk=risk,
                centroid_lat=c_lat,
                centroid_lng=c_lng,
            )
        )
    zones.sort(key=lambda z: (z.risk, z.missing_or_uncertain), reverse=True)
    return PinDesertMapResponse(zones=zones[:top])
