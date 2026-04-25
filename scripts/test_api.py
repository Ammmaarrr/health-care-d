"""End-to-end test that hits POST /query via FastAPI's TestClient."""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from backend.app import app


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "Find emergency surgery hospital in rural Bihar"
    )

    client = TestClient(app)
    print(f"\nQUERY: {q}")
    print("=" * 80)
    resp = client.post("/query", json={"query": q})
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return

    data = resp.json()
    print(f"Results returned: {len(data['results'])}")
    print()

    for hr in data["results"]:
        cap = hr["capabilities"]
        loc = hr["location"]
        print(
            f"  trust={hr['trust_score']:.3f}  "
            f"{hr['name'][:42]:<42}  "
            f"{loc.get('district','?')[:14]:<14}, "
            f"{loc.get('state','?')[:12]:<12}  "
            f"type={hr['meta'].get('facility_type'):<8}  "
            f"emerg={cap['has_emergency']:<10} "
            f"surg={cap['has_surgery']:<10} "
            f"anes={cap['has_anesthesiologist']:<10} "
            f"oxy={cap['has_oxygen']}"
        )

    print()
    print("=== TOP RESULT REASONING ===")
    print(data["results"][0]["reasoning"])
    print()
    print("=== TRACE STEPS ===")
    for s in data["trace"]["steps"]:
        # ASCII-only print for Windows console safety.
        print(" -", s.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
