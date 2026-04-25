"""Smoke-test for /desert-map."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app


def main() -> None:
    client = TestClient(app)
    resp = client.get("/desert-map")
    print("Status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        return
    data = resp.json()
    gaps = data["gaps"]
    print(f"Total gap entries: {len(gaps)}")
    print()
    print("=== TOP 15 (worst gaps; highest missing/uncertain ratio) ===")
    for g in gaps[:15]:
        ratio = g["missing_or_uncertain"] / max(g["total"], 1)
        print(
            f"  {g['state'][:20]:<20}  {g['capability']:<13}  "
            f"missing={g['missing_or_uncertain']:>4}/{g['total']:>4}  ({ratio:.0%})"
        )


if __name__ == "__main__":
    main()
