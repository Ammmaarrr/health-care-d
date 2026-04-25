"""Light text cleaning for hospital notes."""
from __future__ import annotations

import re

import pandas as pd


_WS = re.compile(r"\s+")


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = str(s)
    s = s.replace("\r", " ").replace("\t", " ")
    s = _WS.sub(" ", s)
    return s.strip()


def clean_notes_column(df: pd.DataFrame, col: str = "notes") -> pd.DataFrame:
    df = df.copy()
    df[col] = df[col].map(clean_text)
    return df
