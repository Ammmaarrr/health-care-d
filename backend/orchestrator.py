"""Orchestrates the 7 agents end-to-end and logs everything to MLflow."""
from __future__ import annotations

import time

from backend.agents import (
    extraction_agent,
    query_agent,
    reasoning_agent,
    retrieval_agent,
    trace_agent,
    trust_agent,
    validator_agent,
)
from backend.core import mlflow_setup
from backend.core.schemas import (
    Capabilities,
    Evidence,
    HospitalMeta,
    HospitalResult,
    Location,
    QueryResponse,
    Trace,
)


def _g(row, key, default=None):
    """Safe pandas-Series.get-or-getattr wrapper."""
    try:
        v = row.get(key, default) if hasattr(row, "get") else getattr(row, key, default)
    except Exception:
        v = default
    if v is None:
        return None
    # pandas can give us numpy NaN that isn't None.
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    return v


def _row_location(row) -> Location:
    return Location(
        state=_g(row, "state"),
        district=_g(row, "district"),
        pin=str(_g(row, "pin")) if _g(row, "pin") is not None else None,
        rural=bool(_g(row, "rural")) if _g(row, "rural") is not None else None,
        latitude=float(_g(row, "latitude")) if _g(row, "latitude") is not None else None,
        longitude=float(_g(row, "longitude")) if _g(row, "longitude") is not None else None,
    )


def _row_meta(row) -> HospitalMeta:
    return HospitalMeta(facility_type=_g(row, "facility_type"))


def _row_dict(row) -> dict:
    """Convert a pandas Series-ish row to a plain dict."""
    try:
        return row.to_dict()
    except AttributeError:
        return dict(row)


def run(query: str, *, top_k: int = 8) -> QueryResponse:
    """End-to-end agent pipeline."""
    steps: list[str] = []

    with mlflow_setup.query_run(query):
        # 1. Query understanding.
        t0 = time.time()
        parsed = query_agent.parse_query(query)
        mlflow_setup.log_step("01_parsed_query", parsed.model_dump())
        mlflow_setup.log_metric("query_parse_seconds", time.time() - t0)
        steps.append(f"Parsed query → required: {parsed.required_capabilities}")

        # 2. Retrieval.
        t0 = time.time()
        candidates = retrieval_agent.retrieve(parsed, query, top_k=top_k)
        mlflow_setup.log_step(
            "02_retrieved",
            candidates[["facility_id", "name"]].to_dict(orient="records")
            if "facility_id" in candidates.columns else candidates.head().to_dict(),
        )
        mlflow_setup.log_metric("retrieval_seconds", time.time() - t0)
        steps.append(f"Retrieved {len(candidates)} candidate hospitals.")

        # 3. Extraction (lookup, fall back to live extract).
        caps: list[Capabilities] = []
        evs: list[Evidence] = []
        for _, row in candidates.iterrows():
            looked = extraction_agent.lookup(str(row.get("facility_id", "")))
            if looked is None:
                cap, ev = extraction_agent.extract_one(row.get("notes", "") or "")
            else:
                cap, ev = looked
            caps.append(cap)
            evs.append(ev)
        mlflow_setup.log_step(
            "03_extractions", [c.model_dump() for c in caps]
        )
        steps.append("Extracted capabilities for candidates.")

        # 4. Reasoning / ranking.
        ranked = reasoning_agent.rank(candidates, caps, parsed)
        mlflow_setup.log_step("04_ranking", ranked)
        steps.append(f"Ranked candidates; top score = {ranked[0][1]:.2f}")

        # 5–7 per top result.
        results: list[HospitalResult] = []
        validator_findings = []
        for idx, _ in ranked[:top_k]:
            row = candidates.iloc[idx]
            cap = caps[idx]
            ev = evs[idx]

            v = validator_agent.validate(cap, parsed, use_llm=False)
            trust = trust_agent.score(cap, ev, v)
            location = _row_location(row)
            meta = _row_meta(row)
            reasoning = trace_agent.explain_hospital(
                name=str(_g(row, "name", "Unknown")),
                location=location.model_dump(),
                cap=cap,
                validator=v,
                parsed=parsed,
            )

            evidence_dict = {
                k: getattr(ev, k) for k in ("icu", "emergency", "surgery",
                                            "anesthesiologist", "oxygen", "doctor_type")
                if getattr(ev, k)
            }

            fid = str(_g(row, "facility_id", f"row-{idx}"))
            results.append(
                HospitalResult(
                    facility_id=fid,
                    name=str(_g(row, "name", "Unknown")),
                    location=location,
                    meta=meta,
                    capabilities=cap,
                    trust_score=trust.trust_score,
                    flags=trust.flags,
                    evidence=evidence_dict,
                    reasoning=reasoning,
                )
            )
            validator_findings.append({
                "facility_id": fid,
                "issues": [i.model_dump() for i in v.issues],
                "trust": trust.breakdown.model_dump(),
            })

        mlflow_setup.log_step("05_validator", validator_findings)
        mlflow_setup.log_step("06_results", [r.model_dump() for r in results])

        trace = Trace(
            parsed_query=parsed,
            retrieved_ids=[r.facility_id for r in results],
            validator_findings=validator_findings,
            trust_breakdown={r.facility_id: r.trust_score for r in results},
            steps=steps,
        )
        mlflow_setup.log_step("07_trace", trace.model_dump())

    return QueryResponse(results=results, trace=trace)
