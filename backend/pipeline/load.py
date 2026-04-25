"""Load + canonicalize the raw xlsx into `data/processed/hospitals.parquet`.

We DO NOT hard-code column names yet — the schema for the Virtue Foundation
dataset will be inspected at hour 1 of the build. The output schema we expect
is:

    facility_id: str
    name: str
    state: str | None
    district: str | None
    pin: str | None
    rural: bool | None
    notes: str        # the canonical merged free-text field

Until we've inspected the raw file, this module exposes a single
`canonicalize(df)` function that callers (script 01) will fill in.
"""
from __future__ import annotations

import pandas as pd

from backend.config import settings


REQUIRED_OUT_COLUMNS = ("facility_id", "name", "state", "district", "pin", "rural", "notes")


def load_raw() -> pd.DataFrame:
    return pd.read_excel(settings.raw_path)


def canonicalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Map the raw VF columns to the canonical schema above.

    NOTE: filled in during Hour 1 of the build (TASK.md), once we've
    inspected the actual columns in the xlsx.
    """
    raise NotImplementedError(
        "Implement after inspecting raw columns. See notebooks/01_explore.ipynb."
    )
