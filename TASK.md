# Build Plan — Healthmap Agent

Single source of truth for the 14-hour hackathon build. Update as we go.

---

## 0. Constraints
- **Time:** 14 hours total.
- **LLM budget:** ~$4.50 in OpenAI credits.
- **Provider plan:** OpenAI `gpt-4o-mini` for reasoning, `text-embedding-3-small` for vectors. Architecture stays provider-agnostic via OpenAI-compatible client (we can swap to Groq/Together by changing one env var).
- **Data scale:** 10,000 rows. We process a **stratified sample of 1,000** for the demo to stay well within budget + rate limits. Full 10k toggle exists (`EXTRACTION_SAMPLE_SIZE=0`).
- **Deploy:** backend on Hugging Face Spaces (Docker), frontend on Vercel.

## 1. Cost / rate-limit budget
| Step | Tokens | Est. cost |
|---|---|---|
| Embeddings 10k rows × ~300 tok | 3M | ~$0.06 |
| Batch extraction 1k rows × (600 in + 250 out) tok | 850k | ~$0.25 |
| Batch extraction 10k rows (full)| 8.5M | ~$2.50 |
| Query-time agents (~100 demos × ~2k tok) | ~200k | ~$0.10 |
| **Total demo path (1k sample + 100 queries)** | | **~$0.41** |
| **Total full path (10k + 100 queries)** | | **~$2.66** |

Comfortably inside $4.50.

## 2. Architecture (locked)
```
Frontend (Lovable/v0 → Vercel)
        │  POST {BACKEND_URL}/query
        ▼
FastAPI on Hugging Face Spaces
        │
        ▼ orchestrator.py
   ┌────┴────┐
   1. QueryAgent           — NL → structured intent (LLM)
   2. RetrievalAgent       — FAISS top-K + structured filters (state, rural)
   3. ExtractionAgent      — lookup pre-extracted JSON for top-K
   4. ReasoningAgent       — match capabilities to query, rank
   5. ValidatorAgent       — Tavily standards + rule engine, contradiction flags
   6. TrustAgent           — composite 0–1 score + flags
   7. TraceAgent           — human-readable reasoning string
   └────┬────┘
        │ MLflow run (logs every step)
        ▼
        JSON response

Offline (run once via scripts/):
   load.py → preprocess.py → embed.py → batch_extract.py
```

## 3. API contract (frozen — frontend builds against this)
```
POST /query
Request: { "query": string }
Response: {
  "results": [{
    "facility_id": string,
    "name": string,
    "location": { "state": string, "district": string, "pin": string, "rural": boolean },
    "capabilities": {
      "has_icu":            "yes" | "no" | "uncertain",
      "has_emergency":      "yes" | "no" | "uncertain",
      "has_surgery":        "yes" | "no" | "uncertain",
      "has_anesthesiologist":"yes" | "no" | "uncertain",
      "has_oxygen":         "yes" | "no" | "uncertain",
      "doctor_type":        "full-time" | "part-time" | "unknown"
    },
    "trust_score": number,                        // 0..1
    "flags": string[],                            // e.g. "Surgery claimed but no anesthesiologist"
    "evidence": { [capability: string]: string }, // exact sentence from notes
    "reasoning": string
  }],
  "trace": {
    "parsed_query": object,
    "retrieved_ids": string[],
    "validator_findings": object[],
    "trust_breakdown": object,
    "steps": string[]                             // ordered narrative
  }
}

GET /desert-map
Response: { gaps_by_state: [{ state, missing_capability, count, total }] }

GET /health
Response: { ok: true }
```

## 4. 14-hour timeline
| H | Task | Deliverable | Status |
|---|---|---|---|
| 0–1 | Scaffold repo, push, install deps, dataset peek | repo on GitHub, `data/processed/hospitals.parquet` | ✅ scaffold done |
| 1–2 | FAISS index + RetrievalAgent CLI | `data/index/faiss.index` + working `python -m backend.agents.retrieval_agent "icu rural bihar"` | ⏳ |
| 2–3 | ExtractionAgent + start batch (1k sample) | `data/extracted/capabilities.parquet` populating in background | ⏳ |
| 3–5 | QueryAgent + ReasoningAgent + `/query` end-to-end | curl works, returns ranked results | ⏳ |
| 5–7 | ValidatorAgent (Tavily cache) + TrustAgent + TraceAgent + MLflow | full reasoning chain visible in MLflow UI | ⏳ |
| 7–8 | `/desert-map` aggregation | endpoint returns PIN-level gap data | ⏳ |
| 8–9 | Dockerfile + push to HF Space | live backend URL | ⏳ |
| 9–11 | Lovable/v0 frontend wired to live backend, CORS fix | working demo on vercel.app | ⏳ |
| 11–13 | Polish: gauge UI, MLflow screenshots for deck | demo-ready | ⏳ |
| 13–14 | Buffer / rehearsal | submission | ⏳ |

## 5. Cut order if we fall behind
1. `/desert-map` (drop first)
2. MLflow tracing (replace with simple JSON log)
3. Tavily validation (replace with hardcoded medical rules from `core/medical_rules.py`)
4. Sample size → 200 rows
5. Skip Lovable, use a basic Streamlit UI as fallback

## 6. Prompts (canonical, copy-paste from `backend/core/prompts.py`)
All five LLM prompts live in one file so we can iterate quickly:
1. `QUERY_PROMPT` — NL → structured intent
2. `EXTRACT_PROMPT` — hospital notes → capability JSON (strict, conservative)
3. `VALIDATOR_PROMPT` — capabilities + standards → contradictions
4. `RANK_PROMPT` — short reasoning per hospital (used by ReasoningAgent)
5. `TRACE_PROMPT` — raw trace → human-readable explanation

## 7. Risks + mitigations
| Risk | Mitigation |
|---|---|
| OpenAI rate limit during batch | small concurrency (5–10 workers); resumable batch (skip rows already in parquet) |
| Tavily flakiness | local disk cache; fall back to `medical_rules.py` |
| Dataset column names differ from assumed | `pipeline/load.py` does a column-discovery pass first; we adapt before hard-coding |
| HF Space cold start slow | warm-up ping in frontend on page load |
| Lovable produces broken UI | mock data in `frontend/lib/mock.ts` so demo never blanks |
| Python 3.13 wheel issues | fall back to `py -3.12 -m venv .venv` if `faiss-cpu`/`sentence-transformers` choke |

## 8. Open decisions (none blocking)
- [x] LLM provider: **OpenAI** (locked)
- [x] Embeddings: **OpenAI text-embedding-3-small** (locked, cheap enough)
- [x] Backend host: **HF Spaces** (locked)
- [ ] Frontend tool: Lovable vs v0 — user decides when ready
- [ ] Sample size: default 1000, easy to bump

## 9. Eval criteria → where we score
| Criterion (weight) | Where it shows up |
|---|---|
| Discovery & Verification (35%) | ExtractionAgent's conservative `uncertain` policy; ValidatorAgent contradiction flags; double-check loop |
| IDP Innovation (30%) | Hybrid retrieval + LLM extraction with evidence sentence per capability |
| Social Impact (25%) | `/desert-map` PIN-level gap aggregation |
| UX & Transparency (10%) | TraceAgent + MLflow per-query run + collapsible reasoning UI in frontend |

## 10. Things I (the user) need to do
- [x] Provide OpenAI key
- [x] Provide Tavily key
- [ ] Create Hugging Face account + Space (when prompted at hour 8)
- [ ] Run Lovable/v0 with the prompt below at hour 9
- [ ] Deploy frontend to Vercel
- [ ] **Rotate both API keys after the hackathon** (they were pasted in chat)

## 11. Lovable/v0 prompt (locked)
See `docs/FRONTEND_PROMPT.md` (will be created at hour 9, but the prompt is already drafted in the previous chat turn).
