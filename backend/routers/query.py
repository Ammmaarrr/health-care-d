"""POST /query route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core.schemas import QueryRequest, QueryResponse
from backend.orchestrator import run

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    try:
        return run(
            req.query,
            origin_lat=req.origin_lat,
            origin_lng=req.origin_lng,
            use_llm_validator=req.use_llm_validator,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Backend not ready. Run "
                "`python -m scripts.01_ingest && python -m scripts.02_extract_all` "
                f"first. Missing: {e}"
            ),
        )
