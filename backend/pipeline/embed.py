"""Build the FAISS index from canonical hospital notes."""
from __future__ import annotations

import faiss  # type: ignore
import numpy as np
import pandas as pd

from backend.config import settings
from backend.core.llm import embed


def build_index(df: pd.DataFrame, *, text_col: str = "notes") -> None:
    """Embed `df[text_col]` and write FAISS index + meta parquet to disk."""
    settings.index_path.parent.mkdir(parents=True, exist_ok=True)

    texts = df[text_col].fillna("").astype(str).tolist()
    vecs = np.array(embed(texts), dtype="float32")
    faiss.normalize_L2(vecs)

    index = faiss.IndexFlatIP(vecs.shape[1])  # cosine via inner product on L2-normed vectors
    index.add(vecs)
    faiss.write_index(index, str(settings.index_path))

    # Persist parallel metadata in row order.
    df.reset_index(drop=True).to_parquet(settings.index_meta_path)
