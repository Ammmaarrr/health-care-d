"""One-shot: load xlsx → canonicalize → preprocess → embed → write FAISS.

Run after editing `backend/pipeline/load.py::canonicalize` to map the actual
VF column names. Until then this script will fail with `NotImplementedError`,
which is intentional.

Usage:
    python -m scripts.01_ingest
"""
from __future__ import annotations

from rich import print

from backend.config import settings
from backend.pipeline import embed as embed_pipe
from backend.pipeline import load as load_pipe
from backend.pipeline import preprocess as pp


def main() -> None:
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

    print("[bold]Embedding + building FAISS[/] ...")
    embed_pipe.build_index(df, text_col="notes")
    print(f"  wrote {settings.index_path}")

    print("[bold green]Done.[/]")


if __name__ == "__main__":
    main()
