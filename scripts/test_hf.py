"""Smoke test the deployed HF Space."""
from __future__ import annotations

import sys

import requests

BASE = "https://abdulahadalikhan12-healthmap-agent.hf.space"


def main() -> None:
    print("--- /health ---")
    r = requests.get(f"{BASE}/health", timeout=30)
    print(r.status_code, r.text)

    q = sys.argv[1] if len(sys.argv) > 1 else "Find emergency surgery hospital in rural Bihar"
    print(f"\n--- POST /query  ({q!r}) ---")
    r = requests.post(f"{BASE}/query", json={"query": q}, timeout=180)
    print("Status:", r.status_code)
    if r.status_code != 200:
        print(r.text[:1500])
        return
    data = r.json()
    print(f"Results: {len(data['results'])}")
    for h in data["results"]:
        cap = h["capabilities"]
        loc = h["location"]
        print(
            f"  trust={h['trust_score']:.3f}  "
            f"{h['name'][:42]:<42}  "
            f"state={(loc.get('state') or '?')[:12]:<12}  "
            f"anes={cap['has_anesthesiologist']:<10}  "
            f"oxy={cap['has_oxygen']}"
        )
    print()
    print("Top reasoning:", data["results"][0]["reasoning"])
    print("Trace steps:")
    for s in data["trace"]["steps"]:
        print(" -", s.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
