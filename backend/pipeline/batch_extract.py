"""Batch capability extraction over the dataset.

Three extractor modes:

- ``llm``    OpenAI-compatible LLM extraction (provider-agnostic).
- ``regex``  Pure-regex extractor (mirrors the Databricks notebook).
             Zero API cost, runs in seconds. Lower recall but consistent.
- ``hybrid`` LLM for `hospital` + `clinic` (where free-text notes are
             rich enough to justify the cost), regex for everything else
             (`dentist`, `pharmacy`, `doctor`, etc.). This is the best
             dollars-per-row strategy for the full 10k set.

Other features:
- Resumable: skips facility_ids already present in the output parquet.
- Stratified sampling: tries to cover diverse states evenly when sampling.
- Concurrency: small (5 workers) to avoid OpenAI rate limits.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Literal

import pandas as pd
from tqdm import tqdm

from backend.agents.extraction_agent import (
    _EVIDENCE_FIELDS,
    _TRISTATE_FIELDS,
    extract_one as llm_extract,
)
from backend.config import settings
from backend.core.schemas import Capabilities, Evidence
from backend.pipeline import regex_extract


ExtractorMode = Literal["llm", "regex", "hybrid"]


# Facility types where the free-text notes are detailed enough that LLM
# extraction is usually worth it. Everything else gets the regex path.
_LLM_WORTHY_TYPES = frozenset({"hospital", "clinic"})


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
        extra = df.drop(sampled.index).sample(n - len(sampled), random_state=42)
        sampled = pd.concat([sampled, extra])
    return sampled.reset_index(drop=True)


def _row_to_record(row: dict, cap: Capabilities, ev: Evidence) -> dict:
    out: dict = {
        "facility_id": row["facility_id"],
        "name": row.get("name"),
        "state": row.get("state"),
        "district": row.get("district"),
        "pin": row.get("pin"),
        "rural": row.get("rural"),
        "facility_type": row.get("facility_type"),
        "doctor_type": cap.doctor_type,
    }
    for f in _TRISTATE_FIELDS:
        out[f] = getattr(cap, f)
    for f in _EVIDENCE_FIELDS:
        out[f"ev_{f}"] = getattr(ev, f)
    return out


def _pick_extractor(mode: ExtractorMode, facility_type: str | None) -> Callable[[str], tuple[Capabilities, Evidence]]:
    if mode == "regex":
        return regex_extract.extract_one
    if mode == "llm":
        return llm_extract
    # hybrid: LLM for hospital/clinic, regex for everything else
    ft = (facility_type or "").strip().lower()
    return llm_extract if ft in _LLM_WORTHY_TYPES else regex_extract.extract_one


def _process_row(row: dict, mode: ExtractorMode) -> dict:
    extractor = _pick_extractor(mode, row.get("facility_type"))
    cap, ev = extractor(row.get("notes", "") or "")
    return _row_to_record(row, cap, ev)


def run_batch(
    *,
    sample_size: int | None = None,
    workers: int = 5,
    facility_types: list[str] | None = None,
    extractor: ExtractorMode = "hybrid",
) -> Path:
    """Run capability extraction over (a sample of) the dataset.

    Args:
        sample_size: 0 / None -> process every (filtered) row. Otherwise
            stratified-sample this many rows.
        workers: thread pool size for the LLM path. Regex is fast enough
            that the pool is mostly idle.
        facility_types: optional list of facility_type values to keep.
            Default = no filter (process all 10k rows).
        extractor: see module docstring. Defaults to ``hybrid`` so the
            full 10k can be processed cheaply.
    """
    out = settings.extractions_path
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(settings.processed_path)
    if facility_types:
        df = df[df["facility_type"].isin(facility_types)].reset_index(drop=True)
        print(f"Filtered to facility types {facility_types}: {len(df)} rows.")

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
    print(
        f"Extractor mode: {extractor!r}. "
        f"{sum(1 for r in rows if (r.get('facility_type') or '').lower() in _LLM_WORTHY_TYPES)} "
        f"rows will use LLM, {sum(1 for r in rows if (r.get('facility_type') or '').lower() not in _LLM_WORTHY_TYPES)} regex."
    )

    # Checkpoint cadence -- flush to parquet every N completed rows so
    # a kill / network blip never wastes more than `checkpoint_every`
    # rows of LLM work. Combined with the resume logic above, this makes
    # the whole pipeline crash-tolerant.
    checkpoint_every = max(50, min(500, len(rows) // 20 or 50))

    def _flush(buffer: list[dict]) -> None:
        if not buffer:
            return
        new_df = pd.DataFrame(buffer)
        if out.exists():
            prior = pd.read_parquet(out)
            new_df = pd.concat([prior, new_df], ignore_index=True)
        if "facility_id" in new_df.columns:
            new_df = new_df.drop_duplicates(subset="facility_id", keep="last").reset_index(drop=True)
        new_df.to_parquet(out)

    buffer: list[dict] = []
    if extractor == "regex":
        # Regex is CPU-bound and tiny; sequential is fine and avoids the
        # GIL overhead of a 10k-row thread pool. Still checkpoint so a
        # killed run never costs more than a few seconds.
        for r in tqdm(rows, desc="Regex extracting"):
            try:
                buffer.append(_process_row(r, extractor))
            except Exception as e:
                print(f"  ! row {r.get('facility_id')} failed: {e}")
            if len(buffer) >= checkpoint_every:
                _flush(buffer)
                buffer = []
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_row, r, extractor): r for r in rows}
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Extracting"):
                try:
                    buffer.append(fut.result())
                except Exception as e:
                    r = futures[fut]
                    print(f"  ! row {r.get('facility_id')} failed: {e}")
                if len(buffer) >= checkpoint_every:
                    _flush(buffer)
                    buffer = []

    _flush(buffer)
    return out
