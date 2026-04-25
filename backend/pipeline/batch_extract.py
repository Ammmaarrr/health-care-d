"""Batch capability extraction over the dataset.

- Resumable: skips facility_ids already present in the output parquet.
- Stratified sampling: tries to cover diverse states evenly when sampling.
- Concurrency: small (5 workers) to avoid OpenAI rate limits.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from backend.agents.extraction_agent import extract_one
from backend.config import settings


def _stratified_sample(df: pd.DataFrame, n: int, by: str = "state") -> pd.DataFrame:
    if n <= 0 or n >= len(df):
        return df
    if by not in df.columns:
        return df.sample(n, random_state=42)
    per_group = max(1, n // df[by].nunique())
    sampled = (
        df.groupby(by, group_keys=False)
          .apply(lambda g: g.sample(min(len(g), per_group), random_state=42))
    )
    if len(sampled) > n:
        sampled = sampled.sample(n, random_state=42)
    elif len(sampled) < n:
        # Top up with random rows to hit `n`.
        extra = df.drop(sampled.index).sample(n - len(sampled), random_state=42)
        sampled = pd.concat([sampled, extra])
    return sampled.reset_index(drop=True)


def _process_row(row: dict) -> dict:
    cap, ev = extract_one(row.get("notes", "") or "")
    return {
        "facility_id": row["facility_id"],
        "name": row.get("name"),
        "state": row.get("state"),
        "district": row.get("district"),
        "pin": row.get("pin"),
        "rural": row.get("rural"),
        "facility_type": row.get("facility_type"),
        "has_icu": cap.has_icu,
        "has_emergency": cap.has_emergency,
        "has_surgery": cap.has_surgery,
        "has_anesthesiologist": cap.has_anesthesiologist,
        "has_oxygen": cap.has_oxygen,
        "doctor_type": cap.doctor_type,
        "ev_icu": ev.icu,
        "ev_emergency": ev.emergency,
        "ev_surgery": ev.surgery,
        "ev_anesthesiologist": ev.anesthesiologist,
        "ev_oxygen": ev.oxygen,
        "ev_doctor_type": ev.doctor_type,
    }


def run_batch(*, sample_size: int | None = None, workers: int = 5) -> Path:
    out = settings.extractions_path
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(settings.processed_path)
    if sample_size is None:
        sample_size = settings.extraction_sample_size
    df = _stratified_sample(df, sample_size)

    # Resume support.
    done_ids: set[str] = set()
    if out.exists():
        prior = pd.read_parquet(out)
        done_ids = set(prior["facility_id"].astype(str))
        df = df[~df["facility_id"].astype(str).isin(done_ids)]
        print(f"Resuming: {len(done_ids)} already done, {len(df)} to go.")

    rows = df.to_dict(orient="records")
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_row, r): r for r in rows}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Extracting"):
            try:
                results.append(fut.result())
            except Exception as e:
                r = futures[fut]
                print(f"  ! row {r.get('facility_id')} failed: {e}")

    new_df = pd.DataFrame(results)
    if out.exists():
        prior = pd.read_parquet(out)
        new_df = pd.concat([prior, new_df], ignore_index=True)
    new_df.to_parquet(out)
    return out
