"""GET /desert-map route — aggregates pre-extracted capabilities by state.

Each row carries a Wilson 95% confidence interval on the gap ratio so
NGO planners can distinguish a truly under-served region from a region
whose data is just sparse (Areas-of-Research § 4 in the brief).
"""
from __future__ import annotations

import math

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

# Capability columns we report on. Aligned with `Capabilities` in
# `core.schemas` so /desert-map can show all 11 high-acuity gaps.
_CAP_COLS: tuple[str, ...] = (
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
)

_Z = 1.96  # 95% normal critical value


def _wilson_ci(missing: int, total: int) -> tuple[float, float]:
    """Wilson 95% CI on the proportion `missing / total`. Returns (lo, hi).

    Pure-Python mirror of the Spark expression used in the Databricks
    notebook so judges see the same numbers in either path.
    """
    if total <= 0:
        return 0.0, 0.0
    p = missing / total
    z2 = _Z * _Z
    denom = 1.0 + z2 / total
    centre = (p + z2 / (2 * total)) / denom
    half = (_Z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _missing_or_uncertain_mask(series: pd.Series) -> pd.Series:
    """Robust against missing columns (older cache files) — treat NaN as uncertain."""
    s = series.fillna("uncertain").astype(str)
    return (s == "no") | (s == "uncertain")


@router.get("/desert-map", response_model=DesertMapResponse)
def desert_map(
    min_total: int = Query(5, ge=0, description="Hide groups with fewer than this many facilities."),
    capability: str | None = Query(None, description="Optional filter: 'icu', 'oncology', 'dialysis', etc."),
) -> DesertMapResponse:
    """Aggregated view of capability gaps by state with Wilson 95% CIs."""
    if not settings.extractions_path.exists():
        raise HTTPException(503, "Extractions not built yet.")
    df = pd.read_parquet(settings.extractions_path)
    if "state" not in df.columns:
        raise HTTPException(500, "Extractions missing `state` column.")
    for col in _CAP_COLS:
        if col not in df.columns:
            df[col] = "uncertain"

    cap_filter = capability.lower() if capability else None

    gaps: list[DesertGap] = []
    for state, sub in df.groupby("state"):
        total = int(len(sub))
        if total < min_total:
            continue
        for col in _CAP_COLS:
            cap_name = col.removeprefix("has_")
            if cap_filter and cap_name != cap_filter:
                continue
            missing = int(_missing_or_uncertain_mask(sub[col]).sum())
            lo, hi = _wilson_ci(missing, total)
            gaps.append(DesertGap(
                state=str(state),
                capability=cap_name,
                missing_or_uncertain=missing,
                total=total,
                gap_ratio=round(missing / total, 3) if total else 0.0,
                wilson_lower=round(lo, 3),
                wilson_upper=round(hi, 3),
            ))
    gaps.sort(key=lambda g: g.gap_ratio, reverse=True)
    return DesertMapResponse(gaps=gaps)


@router.get("/desert-map/pins", response_model=PinDesertMapResponse)
def desert_map_pins(
    min_per_pin: int = Query(1, ge=1, description="Hide PINs with fewer than this many facilities."),
    capability: str = Query("icu", description="Capability without the `has_` prefix (icu, surgery, oncology, ...)."),
    top: int = Query(40, ge=1, le=200, description="Return up to this many highest-risk PINs."),
) -> PinDesertMapResponse:
    """PIN-level medical desert / crisis zones for dynamic mapping.

    Joins extraction capabilities with processed lat/lng + PIN. `risk` is the
    fraction of facilities in that PIN that are `no` or `uncertain` on the axis.
    Wilson 95% CI on `risk` is also returned.
    """
    if not settings.extractions_path.exists():
        raise HTTPException(503, "Extractions not built yet.")
    if not settings.processed_path.exists():
        raise HTTPException(503, "Processed hospitals not built yet.")

    ex = pd.read_parquet(settings.extractions_path)
    pr = pd.read_parquet(settings.processed_path)
    cap = capability.lower()
    key = cap if cap.startswith("has_") else f"has_{cap}"
    if key not in _CAP_COLS:
        raise HTTPException(400, f"Unknown capability / column: {key}")
    if key not in ex.columns:
        ex[key] = "uncertain"
    if "state" not in ex.columns and "state" in pr.columns:
        ex = ex.merge(pr[["facility_id", "state"]], on="facility_id", how="left")

    # `ex` already carries its own `pin` from batch_extract, but the
    # authoritative PIN+lat/lng live in `processed`. Drop the duplicate
    # before merging so we don't end up with `pin_x` / `pin_y`.
    ex_no_pin = ex.drop(columns=[c for c in ("pin",) if c in ex.columns])
    merged = ex_no_pin.merge(
        pr[["facility_id", "pin", "latitude", "longitude"]],
        on="facility_id",
        how="left",
    )
    merged["pin"] = merged["pin"].fillna("").astype(str).str.strip()
    merged = merged[merged["pin"].str.len() > 0]

    cap_label = key.removeprefix("has_")
    zones: list[PinDesertGap] = []
    for pin, sub in merged.groupby("pin"):
        pin_s = str(pin).strip()
        if not pin_s:
            continue
        n = int(len(sub))
        if n < min_per_pin:
            continue
        miss = int(_missing_or_uncertain_mask(sub[key]).sum())
        risk = round(miss / n, 3) if n else 0.0
        lo, hi = _wilson_ci(miss, n)
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
        zones.append(PinDesertGap(
            pin=pin_s,
            state=stv,
            capability=cap_label,
            total=n,
            missing_or_uncertain=miss,
            risk=risk,
            wilson_lower=round(lo, 3),
            wilson_upper=round(hi, 3),
            centroid_lat=c_lat,
            centroid_lng=c_lng,
        ))
    zones.sort(key=lambda z: (z.risk, z.missing_or_uncertain), reverse=True)
    return PinDesertMapResponse(zones=zones[:top])
