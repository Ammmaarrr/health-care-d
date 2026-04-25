"""Quick end-to-end smoke test (used during development)."""
from __future__ import annotations

import sys

from rich import print

from backend.agents.extraction_agent import extract_one
from backend.agents.query_agent import parse_query
from backend.agents.reasoning_agent import rank
from backend.agents.retrieval_agent import retrieve
from backend.agents.trust_agent import score
from backend.agents.validator_agent import validate


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else (
        "Find emergency surgery hospital in rural Bihar with part-time doctors"
    )
    print(f"[bold]Query:[/] {q}\n")

    parsed = parse_query(q)
    print("[bold]Parsed:[/]", parsed.model_dump())
    print()

    cands = retrieve(parsed, q, top_k=5)
    print(f"[bold]Retrieved[/] {len(cands)} candidates:")
    for _, row in cands.iterrows():
        name = str(row["name"])[:50]
        state = str(row["state"])[:15]
        ftype = str(row["facility_type"])[:10]
        print(
            f"  [{row['facility_id']}] {name:<50}  state={state:<15} "
            f"type={ftype:<10} rural={row['rural']} score={row['_score']:.3f}"
        )

    # Live extract just the top candidate to validate the agent works.
    print()
    top = cands.iloc[0]
    print(f"[bold]Live-extracting capabilities for [/]{top['name']}")
    cap, ev = extract_one(str(top["notes"]))
    print("  Capabilities:", cap.model_dump())
    print("  Evidence (first non-empty):", next(
        (f"{k}: {v}" for k, v in ev.model_dump().items() if v), "(none)"
    ))

    # Reason / validate / score for the top one.
    caps = [cap]
    ranked = rank(cands.head(1).reset_index(drop=True), caps, parsed)
    print("\n[bold]Ranked:[/]", ranked)
    v = validate(cap, parsed, use_llm=False)
    print("[bold]Validator (rules-only):[/]", v.model_dump())
    t = score(cap, ev, v)
    print("[bold]Trust:[/]", t.model_dump())


if __name__ == "__main__":
    main()
