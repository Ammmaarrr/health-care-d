"""Pydantic models — frozen API contract.

Frontend (Lovable / v0) builds against these field names. Do not rename
without updating `TASK.md` § 3 and the frontend.

The capability vocabulary covers the MVP requirements (ICU, emergency,
surgery, anesthesiologist, oxygen) and the high-acuity specialties the
brief explicitly calls out — Oncology, Dialysis, Neonatal, Emergency
Trauma — plus two supporting infrastructure capabilities (lab, imaging)
that the validator agent uses to flag contradictions.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Capability primitives
# --------------------------------------------------------------------------- #
TriState = Literal["yes", "no", "uncertain"]
DoctorType = Literal["full-time", "part-time", "unknown"]


# Tokens accepted in `ParsedQuery.required_capabilities` and
# emitted by `ExtractionAgent` (each maps to a `has_*` field below).
CAPABILITY_TOKENS: tuple[str, ...] = (
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
)


class Capabilities(BaseModel):
    """Conservative capability extraction. 'uncertain' is the safe default."""

    has_icu: TriState = "uncertain"
    has_emergency: TriState = "uncertain"
    has_surgery: TriState = "uncertain"
    has_anesthesiologist: TriState = "uncertain"
    has_oxygen: TriState = "uncertain"
    # High-acuity specialties the brief calls out by name.
    has_oncology: TriState = "uncertain"
    has_dialysis: TriState = "uncertain"
    has_neonatal: TriState = "uncertain"
    has_trauma: TriState = "uncertain"
    # Supporting infrastructure used by the validator.
    has_lab: TriState = "uncertain"
    has_imaging: TriState = "uncertain"
    doctor_type: DoctorType = "unknown"


class Evidence(BaseModel):
    """Per-capability supporting sentence from the hospital's notes."""

    icu: str | None = None
    emergency: str | None = None
    surgery: str | None = None
    anesthesiologist: str | None = None
    oxygen: str | None = None
    oncology: str | None = None
    dialysis: str | None = None
    neonatal: str | None = None
    trauma: str | None = None
    lab: str | None = None
    imaging: str | None = None
    doctor_type: str | None = None


# --------------------------------------------------------------------------- #
# Query → structured intent
# --------------------------------------------------------------------------- #
class ParsedQuery(BaseModel):
    location: str | None = None
    state: str | None = None
    district: str | None = None
    rural: bool | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    # Explicit doctor preference (e.g. "part-time doctors" in the brief's
    # example query). null when the user did not constrain it.
    doctor_preference: DoctorType | None = None


# --------------------------------------------------------------------------- #
# Validator output
# --------------------------------------------------------------------------- #
class ValidatorIssue(BaseModel):
    capability: str
    issue: str
    severity: Literal["low", "medium", "high"] = "medium"


class ValidatorResult(BaseModel):
    valid: bool
    issues: list[ValidatorIssue] = Field(default_factory=list)
    confidence_adjustment: float = 0.0  # range: -0.5 .. 0


# --------------------------------------------------------------------------- #
# Trust scoring
# --------------------------------------------------------------------------- #
class TrustBreakdown(BaseModel):
    completeness: float
    consistency: float
    validator: float
    evidence_strength: float


class TrustResult(BaseModel):
    trust_score: float  # 0..1
    flags: list[str] = Field(default_factory=list)
    breakdown: TrustBreakdown


# --------------------------------------------------------------------------- #
# Hospital location
# --------------------------------------------------------------------------- #
class Location(BaseModel):
    state: str | None = None
    district: str | None = None
    pin: str | None = None
    rural: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


class HospitalMeta(BaseModel):
    """Non-clinical metadata returned per result."""

    facility_type: str | None = None  # hospital, clinic, dentist, pharmacy, doctor


# --------------------------------------------------------------------------- #
# Top-level result + trace (returned by /query)
# --------------------------------------------------------------------------- #
class HospitalResult(BaseModel):
    facility_id: str
    name: str
    location: Location
    meta: HospitalMeta = Field(default_factory=HospitalMeta)
    capabilities: Capabilities
    trust_score: float
    flags: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)
    reasoning: str
    phone: str | None = None
    email: str | None = None
    """Decomposed inputs to `trust_score` (for row-level agentic traceability)."""
    trust_breakdown: TrustBreakdown
    # Optional Haversine distance from a user-supplied origin. Only set
    # when the request includes `origin_lat` + `origin_lng`.
    distance_km: float | None = None


class Trace(BaseModel):
    parsed_query: ParsedQuery
    retrieved_ids: list[str] = Field(default_factory=list)
    validator_findings: list[dict] = Field(default_factory=list)
    trust_breakdown: dict = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    # Token / cost summary for the whole run, populated by the orchestrator.
    cost: dict[str, float] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    query: str
    # Optional anchor for "nearest" reasoning. Both must be set together.
    origin_lat: float | None = None
    origin_lng: float | None = None
    # Toggle the more expensive validator LLM cross-check on the top-K
    # results (defaults true; set to false for fast demos).
    use_llm_validator: bool = True


class QueryResponse(BaseModel):
    results: list[HospitalResult]
    trace: Trace


# --------------------------------------------------------------------------- #
# /desert-map response
# --------------------------------------------------------------------------- #
class DesertGap(BaseModel):
    state: str
    capability: str
    missing_or_uncertain: int
    total: int
    gap_ratio: float
    # Wilson 95% confidence interval on `gap_ratio`. Lets NGO planners
    # distinguish a truly under-served region from a region with sparse
    # data. (Areas-of-Research § 4 in the brief.)
    wilson_lower: float
    wilson_upper: float


class DesertMapResponse(BaseModel):
    gaps: list[DesertGap]


class PinDesertGap(BaseModel):
    """Per-PIN risk for crisis / desert mapping."""

    pin: str
    state: str | None
    capability: str
    total: int
    missing_or_uncertain: int
    risk: float
    wilson_lower: float
    wilson_upper: float
    centroid_lat: float | None
    centroid_lng: float | None


class PinDesertMapResponse(BaseModel):
    zones: list[PinDesertGap]
