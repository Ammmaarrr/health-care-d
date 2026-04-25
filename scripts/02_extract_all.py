"""Run capability extraction over (a sample of) the dataset.

Usage:
    python -m scripts.02_extract_all              # uses EXTRACTION_SAMPLE_SIZE from .env
    python -m scripts.02_extract_all --all        # process every row
    python -m scripts.02_extract_all --n 200      # process N rows
"""
from __future__ import annotations

import argparse

from rich import print

from backend.config import settings
from backend.pipeline.batch_extract import run_batch


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=None, help="Sample size override.")
    p.add_argument("--all", action="store_true", help="Process every row.")
    p.add_argument("--workers", type=int, default=5)
    args = p.parse_args()

    n = 0 if args.all else (args.n if args.n is not None else settings.extraction_sample_size)
    print(f"[bold]Batch extraction[/] sample_size={n if n else 'ALL'} workers={args.workers}")
    out = run_batch(sample_size=n, workers=args.workers)
    print(f"[bold green]Done.[/] Wrote {out}")


if __name__ == "__main__":
    main()
