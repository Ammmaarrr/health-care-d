"""Smoke test the deployed /desert-map endpoint."""
from __future__ import annotations

import requests

BASE = "https://abdulahadalikhan12-healthmap-agent.hf.space"


def main() -> None:
    r = requests.get(f"{BASE}/desert-map", params={"min_total": 30}, timeout=30)
    print("Status:", r.status_code)
    if r.status_code != 200:
        print(r.text[:1500])
        return
    data = r.json()
    gaps = data["gaps"]
    print(f"Total entries: {len(gaps)}")
    print("Top 10 worst gaps:")
    for g in gaps[:10]:
        print(
            f"  {g['state'][:18]:<18} {g['capability']:<14} "
            f"missing={g['missing_or_uncertain']:>4}/{g['total']:>4}  "
            f"ratio={g['gap_ratio']:.0%}"
        )


if __name__ == "__main__":
    main()
