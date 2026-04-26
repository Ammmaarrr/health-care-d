"""Agent 2 — Retrieval.

Two retrieval backends, picked at runtime:

- **FAISS** (default) — local index built by `pipeline.embed.build_index`.
  Zero infra, runs anywhere (HF Spaces, laptop, CI).
- **Mosaic AI Vector Search** — Databricks-managed, used when both
  ``VECTOR_SEARCH_ENDPOINT`` and ``VECTOR_SEARCH_INDEX`` are set in
  the environment. Lazy-imported so non-Databricks installs do not
  need the SDK.

Hybrid query: structured filter on parsed query (state, rural) + dense
vector top-K, then re-rank.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import faiss  # type: ignore
import numpy as np
import pandas as pd

from backend.config import settings
from backend.core.llm import embed
from backend.core.mlflow_setup import trace_step
from backend.core.schemas import ParsedQuery


# --------------------------------------------------------------------------- #
# FAISS backend (local default)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_faiss() -> tuple[Any, pd.DataFrame]:
    """Load FAISS index + parallel metadata frame."""
    index = faiss.read_index(str(settings.index_path))
    meta = pd.read_parquet(settings.index_meta_path)
    return index, meta


def _faiss_search(query_text: str, k: int) -> pd.DataFrame:
    index, meta = _load_faiss()
    qvec = np.array(embed([query_text])[0], dtype="float32")[None, :]
    faiss.normalize_L2(qvec)
    scores, idx = index.search(qvec, k)
    out = meta.iloc[idx[0]].copy()
    out["_score"] = scores[0]
    return out


# --------------------------------------------------------------------------- #
# Mosaic AI Vector Search backend (Databricks)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_vector_search_index() -> Any:
    """Lazy-import the Databricks SDK only when configured."""
    try:
        from databricks.vector_search.client import VectorSearchClient  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "databricks-vectorsearch is not installed. "
            "Run `pip install databricks-vectorsearch` "
            "or unset VECTOR_SEARCH_ENDPOINT to fall back to FAISS."
        ) from e

    client = VectorSearchClient()
    return client.get_index(
        endpoint_name=settings.vector_search_endpoint,
        index_name=settings.vector_search_index,
    )


def _vs_search(query_text: str, k: int, parsed: ParsedQuery) -> pd.DataFrame:
    """Hybrid query against Mosaic AI Vector Search.

    The index must have been built from `facilities_clean` with
    `notes` as the text column (see databricks/notebooks/04_vector_search.py).
    Structured filters are pushed down to the index when possible.
    """
    idx = _load_vector_search_index()
    filters: dict[str, Any] = {}
    if parsed.state:
        filters["state"] = parsed.state
    if parsed.rural is True:
        filters["rural"] = True

    response = idx.similarity_search(
        query_text=query_text,
        columns=[
            "facility_id", "name", "state", "district", "pin", "rural",
            "latitude", "longitude", "facility_type", "phone", "email", "notes",
        ],
        num_results=k,
        filters=filters or None,
    )
    rows = (response or {}).get("result", {}).get("data_array") or []
    cols = [c["name"] for c in (response or {}).get("manifest", {}).get("columns", [])]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=cols)
    # The score column from VS is usually called "score" or "_score".
    if "score" in df.columns:
        df = df.rename(columns={"score": "_score"})
    elif "_score" not in df.columns:
        df["_score"] = 1.0
    return df


def _backend_in_use() -> str:
    if settings.vector_search_endpoint and settings.vector_search_index:
        return "mosaic_vector_search"
    return "faiss"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _structured_filter(meta: pd.DataFrame, parsed: ParsedQuery) -> pd.Series:
    mask = pd.Series(True, index=meta.index)
    if parsed.state and "state" in meta.columns:
        mask &= meta["state"].fillna("").str.lower().str.contains(parsed.state.lower())
    if parsed.district and "district" in meta.columns:
        mask &= meta["district"].fillna("").str.lower().str.contains(parsed.district.lower())
    if parsed.rural is True and "rural" in meta.columns:
        mask &= meta["rural"].fillna(False).astype(bool)
    return mask


@trace_step("retrieval")
def retrieve(parsed: ParsedQuery, query_text: str, *, top_k: int = 10) -> pd.DataFrame:
    """Retrieve candidates from whichever backend is configured."""
    backend = _backend_in_use()

    if backend == "mosaic_vector_search":
        try:
            candidates = _vs_search(query_text, top_k * 4, parsed)
        except Exception as e:
            print(f"[retrieval] Mosaic VS failed ({e}); falling back to FAISS.")
            candidates = _faiss_search(query_text, top_k * 8)
    else:
        candidates = _faiss_search(query_text, top_k * 8)

    mask = _structured_filter(candidates, parsed)
    filtered = candidates[mask]

    # If the user pinned a state and we found ANY matches there, return
    # only those — even if fewer than top_k. Avoids leakage across states.
    if parsed.state and len(filtered) > 0:
        return filtered.head(top_k).reset_index(drop=True)

    if len(filtered) < top_k:
        filtered = candidates
    return filtered.head(top_k).reset_index(drop=True)
