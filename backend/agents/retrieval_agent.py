"""Agent 2 — Retrieval.

Hybrid: structured filter on parsed query (state, rural) + FAISS top-K vector
search over hospital notes. Loads the FAISS index lazily on first call.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import faiss  # type: ignore
import numpy as np
import pandas as pd

from backend.config import settings
from backend.core.llm import embed
from backend.core.schemas import ParsedQuery


@lru_cache(maxsize=1)
def _load_index() -> tuple[Any, pd.DataFrame]:
    """Load FAISS index + parallel metadata frame."""
    index = faiss.read_index(str(settings.index_path))
    meta = pd.read_parquet(settings.index_meta_path)
    return index, meta


def _structured_filter(meta: pd.DataFrame, parsed: ParsedQuery) -> pd.Series:
    mask = pd.Series(True, index=meta.index)
    if parsed.state and "state" in meta.columns:
        mask &= meta["state"].fillna("").str.lower().str.contains(parsed.state.lower())
    if parsed.district and "district" in meta.columns:
        mask &= meta["district"].fillna("").str.lower().str.contains(parsed.district.lower())
    if parsed.rural is True and "rural" in meta.columns:
        mask &= meta["rural"].fillna(False).astype(bool)
    return mask


def retrieve(parsed: ParsedQuery, query_text: str, *, top_k: int = 10) -> pd.DataFrame:
    index, meta = _load_index()

    # Vector search.
    qvec = np.array(embed([query_text])[0], dtype="float32")[None, :]
    faiss.normalize_L2(qvec)
    # Search a wider net so we have enough rows after filtering.
    scores, idx = index.search(qvec, top_k * 5)
    candidates = meta.iloc[idx[0]].copy()
    candidates["_score"] = scores[0]

    # Apply structured filter.
    mask = _structured_filter(candidates, parsed)
    filtered = candidates[mask]
    if len(filtered) < top_k:
        # Fall back to unfiltered candidates so we always return something.
        filtered = candidates
    return filtered.head(top_k).reset_index(drop=True)
