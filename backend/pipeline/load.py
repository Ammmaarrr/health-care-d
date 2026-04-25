"""Load + canonicalize the Virtue Foundation India 10k dataset.

Output schema (locked, used by everything downstream):

    facility_id    str            "vf-00000" .. "vf-09999"
    name           str
    state          str | None
    district       str | None     (we use city as district proxy)
    pin            str | None
    rural          bool | None    (heuristic: not a Tier-1/2 city)
    latitude       float | None
    longitude      float | None
    facility_type  str | None     ('hospital','clinic','dentist',...)
    notes          str            merged free-text field, the source of truth
                                  for ExtractionAgent
"""
from __future__ import annotations

import ast

import pandas as pd

from backend.config import settings


REQUIRED_OUT_COLUMNS = (
    "facility_id", "name", "state", "district", "pin", "rural",
    "latitude", "longitude", "facility_type", "notes",
)


# Tier-1 + Tier-2 Indian cities (lowercased). Anything not on this list is
# treated as rural for the purpose of the `rural` flag.
_URBAN_CITIES: frozenset[str] = frozenset({
    # Tier-1
    "mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "hyderabad",
    "chennai", "kolkata", "pune", "ahmedabad",
    # Tier-2 (selected; covers ~80% of urban facilities)
    "surat", "jaipur", "lucknow", "kanpur", "nagpur", "visakhapatnam",
    "indore", "thane", "bhopal", "patna", "vadodara", "ghaziabad", "ludhiana",
    "coimbatore", "agra", "madurai", "nashik", "faridabad", "meerut",
    "rajkot", "kalyan", "vasai", "vijayawada", "jabalpur", "mysore",
    "mysuru", "gwalior", "aurangabad", "ranchi", "howrah", "jodhpur",
    "raipur", "kota", "guwahati", "chandigarh", "dehradun", "noida",
    "gurgaon", "gurugram", "amritsar", "allahabad", "prayagraj", "varanasi",
    "srinagar", "navi mumbai", "ulhasnagar", "tiruchirappalli", "trichy",
    "salem", "warangal", "ranchi", "kochi", "cochin", "thiruvananthapuram",
    "trivandrum", "kozhikode", "calicut", "thrissur",
})


def load_raw() -> pd.DataFrame:
    return pd.read_excel(settings.raw_path)


def _format_list_field(val: object, label: str) -> str:
    """JSON-like list strings → flat readable text. Empty / null → ''."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan" or s in ("[]", "['']", "[\"\"]"):
        return ""
    # Try parsing JSON-list-ish strings.
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            items = [str(x).strip() for x in parsed if str(x).strip()]
            if not items:
                return ""
            return f"{label}: " + "; ".join(items) + "."
    except (ValueError, SyntaxError):
        pass
    return f"{label}: {s}."


def _build_notes(row: pd.Series) -> str:
    parts: list[str] = []
    desc = str(row.get("description") or "").strip()
    if desc and desc.lower() != "nan":
        parts.append(f"Description: {desc}")

    parts.append(_format_list_field(row.get("specialties"), "Specialties"))
    parts.append(_format_list_field(row.get("procedure"), "Procedures"))
    parts.append(_format_list_field(row.get("equipment"), "Equipment"))
    parts.append(_format_list_field(row.get("capability"), "Capabilities listed"))

    ftype = row.get("facilityTypeId")
    if ftype and str(ftype).strip().lower() != "nan":
        parts.append(f"Facility type: {ftype}.")
    op = row.get("operatorTypeId")
    if op and str(op).strip().lower() != "nan":
        parts.append(f"Operator type: {op}.")

    return " ".join(p for p in parts if p)


def _is_rural(city: object) -> bool | None:
    if city is None or (isinstance(city, float) and pd.isna(city)):
        return None
    return str(city).strip().lower() not in _URBAN_CITIES


def canonicalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Map VF columns → our canonical schema."""
    out = pd.DataFrame()
    out["facility_id"] = [f"vf-{i:05d}" for i in range(len(raw))]
    out["name"] = raw["name"].astype(str).str.strip()
    out["state"] = raw["address_stateOrRegion"].astype(str).str.strip()
    out["district"] = raw["address_city"].astype(str).str.strip()
    out["pin"] = raw["address_zipOrPostcode"].astype(str).str.strip().replace({"nan": None})
    out["rural"] = raw["address_city"].apply(_is_rural)
    out["latitude"] = raw["latitude"]
    out["longitude"] = raw["longitude"]
    out["facility_type"] = raw["facilityTypeId"].astype(str).str.strip().replace({"nan": None})
    out["notes"] = raw.apply(_build_notes, axis=1)
    return out
