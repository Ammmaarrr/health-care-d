"""Set Hugging Face Space secrets via the API.

Reads OPENAI_API_KEY and TAVILY_API_KEY from your local .env, plus an
HF write token + Space repo id from CLI args, and uploads them as
Space secrets. After this, restart the Space (or it will rebuild
automatically) and the FastAPI app can read them at runtime.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-id", required=True, help="e.g. abdulahadalikhan12/healthmap-agent")
    p.add_argument(
        "--token",
        default="",
        help="HF write token; if omitted, uses HUGGINGFACE_HUB_TOKEN or HF_TOKEN in .env",
    )
    p.add_argument("--cors-origins", default="http://localhost:3000",
                   help="Comma-separated origins for the FastAPI CORS middleware.")
    args = p.parse_args()

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
    if not (args.token or "").strip():
        args.token = (os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN") or "").strip()
    if not args.token:
        print("ERROR: pass --token or set HUGGINGFACE_HUB_TOKEN in .env", file=sys.stderr)
        sys.exit(1)
    openai_key = os.getenv("OPENAI_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not openai_key or not tavily_key:
        print("ERROR: OPENAI_API_KEY and TAVILY_API_KEY must be in .env", file=sys.stderr)
        sys.exit(1)

    api = HfApi(token=args.token)

    secrets = {
        "OPENAI_API_KEY": openai_key,
        "TAVILY_API_KEY": tavily_key,
        "CORS_ORIGINS": args.cors_origins,
    }
    for key, value in secrets.items():
        api.add_space_secret(repo_id=args.repo_id, key=key, value=value)
        print(f"  set {key}  ({len(value)} chars)")

    print(f"\nDone. Restarting Space {args.repo_id} ...")
    try:
        api.restart_space(repo_id=args.repo_id)
        print("  restart triggered.")
    except Exception as e:
        print(f"  could not auto-restart ({e}); the Space will rebuild on next push or "
              f"you can click 'Restart Space' in the UI.")


if __name__ == "__main__":
    main()
