"""Pydantic models — frozen API contract.

Frontend (Lovable / v0) builds against these field names. Do not rename
without updating `TASK.md` § 3 and the frontend.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Capability primitives
# --------------------------------------------------------------------------- #
TriState = Literal["yes", "no", "uncertain"]
DoctorType = Literal["full-time", "part-time", "unknown"]


class Capabilities(BaseModel):
    """Conservative capability extraction. 'uncertain' is the safe default."""

    has_icu: TriState = "uncertain"
    has_emergency: TriState = "uncertain"
    has_surgery: TriState = "uncertain"
    has_anesthesiologist: TriState = "uncertain"
    has_oxygen: TriState = "uncertain"
    doctor_type: DoctorType = "unknown"


class Evidence(BaseModel):
    """Per-capability supporting sentence from the hospital's notes."""

    icu: str | None = None
    emergency: str | None = None
    surgery: str | None = None
    anesthesiologist: str | None = None
    oxygen: str | None = None
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


class Trace(BaseModel):
    parsed_query: ParsedQuery
    retrieved_ids: list[str] = Field(default_factory=list)
    validator_findings: list[dict] = Field(default_factory=list)
    trust_breakdown: dict = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    query: str


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
    centroid_lat: float | None
    centroid_lng: float | None


class PinDesertMapResponse(BaseModel):
    zones: list[PinDesertGap]
