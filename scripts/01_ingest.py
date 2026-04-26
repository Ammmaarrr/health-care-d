"""One-shot: load xlsx -> canonicalize -> preprocess -> embed -> write FAISS.

Usage:
    python -m scripts.01_ingest                  # full pipeline (requires LLM provider key)
    python -m scripts.01_ingest --skip-embed     # parquet only (no API needed)
"""
from __future__ import annotations

import argparse

from rich import print

from backend.config import settings
from backend.pipeline import embed as embed_pipe
from backend.pipeline import load as load_pipe
from backend.pipeline import preprocess as pp


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip the FAISS embedding step. Useful when no LLM provider key is available; you can run regex extraction on the parquet without it.",
    )
    args = p.parse_args()

    print(f"[bold]Loading[/] {settings.raw_path}")
    raw = load_pipe.load_raw()
    print(f"  rows={len(raw)}  cols={list(raw.columns)}")

    print("[bold]Canonicalizing[/] ...")
    df = load_pipe.canonicalize(raw)

    missing = [c for c in load_pipe.REQUIRED_OUT_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"Canonical frame is missing columns: {missing}")

    print("[bold]Cleaning notes[/] ...")
    df = pp.clean_notes_column(df, "notes")

    settings.processed_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(settings.processed_path)
    print(f"  wrote {settings.processed_path}")

    if args.skip_embed:
        print("[yellow]Skipping FAISS index build[/] (--skip-embed). "
              "Run again without the flag once a provider key is in .env.")
    else:
        print("[bold]Embedding + building FAISS[/] ...")
        embed_pipe.build_index(df, text_col="notes")
        print(f"  wrote {settings.index_path}")

    print("[bold green]Done.[/]")


if __name__ == "__main__":
    main()
