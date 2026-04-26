"""Run capability extraction over (a sample of) the dataset.

Usage:
    python -m scripts.02_extract_all                      # default: hybrid extractor, full 10k rows
    python -m scripts.02_extract_all --extractor llm      # LLM for every row (more accurate, more $$)
    python -m scripts.02_extract_all --extractor regex    # zero-cost regex baseline
    python -m scripts.02_extract_all --n 1000             # stratified sample of 1000
    python -m scripts.02_extract_all --types hospital,clinic
"""
from __future__ import annotations

import argparse

from rich import print

from backend.config import settings
from backend.pipeline.batch_extract import ExtractorMode, run_batch


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=None, help="Sample size override (0 = all rows).")
    p.add_argument(
        "--all",
        action="store_true",
        help="Process every (post-filter) row. Equivalent to --n 0.",
    )
    p.add_argument("--workers", type=int, default=5)
    p.add_argument(
        "--types",
        default="",
        help=(
            "Comma-separated facility types to include. Empty = all 10k rows "
            "(hospital, clinic, dentist, pharmacy, doctor)."
        ),
    )
    p.add_argument(
        "--extractor",
        choices=("llm", "regex", "hybrid"),
        default="hybrid",
        help=(
            "How to extract capabilities. `hybrid` (default) uses the LLM for "
            "hospital/clinic rows and regex for everything else."
        ),
    )
    args = p.parse_args()

    n = 0 if args.all else (args.n if args.n is not None else settings.extraction_sample_size)
    types = [t.strip() for t in args.types.split(",") if t.strip()] if args.types else None
    mode: ExtractorMode = args.extractor  # type: ignore[assignment]

    print(
        f"[bold]Batch extraction[/] sample_size={n if n else 'ALL'} "
        f"workers={args.workers} types={types or 'ALL'} "
        f"extractor={mode} provider={settings.llm_provider} model={settings.resolved_llm_model}"
    )
    out = run_batch(
        sample_size=n,
        workers=args.workers,
        facility_types=types,
        extractor=mode,
    )
    print(f"[bold green]Done.[/] Wrote {out}")


if __name__ == "__main__":
    main()
