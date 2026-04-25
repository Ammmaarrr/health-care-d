"""FastAPI entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import desert, query


app = FastAPI(
    title="Healthmap Agent",
    description="Agentic Healthcare Intelligence System for the India 10k dataset.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, tags=["agents"])
app.include_router(desert.router, tags=["analytics"])


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
