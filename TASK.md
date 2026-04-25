# Build Plan — Healthmap Agent

Single source of truth for the 14-hour hackathon build. Updated as we go.

---

## 0. Constraints
- **Time:** 14 hours total.
- **LLM budget:** ~$4.50 in OpenAI credits.
- **Provider:** OpenAI `gpt-4o-mini` for reasoning, `text-embedding-3-small` for vectors. Architecture stays provider-agnostic via OpenAI-compatible client.
- **Data scale:** 10,000 rows. Demo runs on the **2,789 hospitals** (where ICU/surgery/emergency questions actually have answers). Toggle via `--types` flag on the batch script.
- **Deploy:** backend on Hugging Face Spaces (Docker), frontend on Vercel.

## 1. Cost / rate-limit budget — actual spent
| Step | Tokens | Est. cost | Status |
|---|---|---|---|
| Embeddings 10k rows | 1.5M | ~$0.03 | ✅ done |
| Batch extraction 1k stratified sample | 850k | ~$0.20 | ✅ done |
| Batch extraction all 2,789 hospitals (running) | ~2M | ~$0.65 | ⏳ in progress |
| Per-query agents (live testing) | ~50k | ~$0.05 | ✅ done |
| **Total spent so far** | | **~$0.93** | |
| **Budget remaining** | | **~$3.55** | |

Comfortably inside $4.50.

## 2. Architecture (locked)
```
Frontend (Lovable/v0 → Vercel)
        │  POST {BACKEND_URL}/query
        ▼
FastAPI on Hugging Face Spaces (Docker, port 7860)
        │
        ▼ orchestrator.py
   ┌────┴────┐
   1. QueryAgent           — NL → structured intent (LLM)
   2. RetrievalAgent       — FAISS top-K + structured filters (state, rural)
   3. ExtractionAgent      — disk + memory cache, parallel live fallback
   4. ValidatorAgent       — Tavily standards (cached) + rule engine
   5. TrustAgent           — completeness × consistency × validator × evidence
   6. ReasoningAgent       — combined ranking: 0.6*match + 0.4*trust
   7. TraceAgent           — per-hospital LLM reasoning + structured Trace
   └────┬────┘
        │ MLflow run (one per /query)
        ▼
        JSON response
```

## 3. Build progress (ahead of schedule)
| H | Task | Status | Deliverable |
|---|---|---|---|
| 0–1 | Scaffold, push, deps | ✅ | repo on GitHub, venv, all deps installed |
| 1–2 | Canonicalize 10k → parquet, FAISS index, retrieval | ✅ | `data/processed/hospitals.parquet`, `data/index/faiss.index` |
| 2–3 | ExtractionAgent + 1000-row stratified sample | ✅ | `data/extracted/capabilities.parquet` |
| 3–5 | Query/Reasoning/Validator/Trust/Trace agents + `/query` | ✅ | end-to-end live: 10s cached, 17s cold |
| 5–7 | MLflow tracing + Tavily caching + medical rules | ✅ | mlruns/ logged per query, tavily_cache/ active |
| 7–8 | `/desert-map` with min_total filter | ✅ | endpoint live, returns gap_ratio per state |
| 8–9 | Dockerfile + HF Spaces deploy script | ✅ | `scripts/deploy_hf.ps1` ready |
| 8–9 | **Wider batch over all 2,789 hospitals** | ⏳ | running in background |
| 9–11 | Lovable/v0 frontend wired to live backend | ⏳ | waiting on user action |
| 11–13 | Polish: gauge UI, MLflow screenshots | ⏳ | |
| 13–14 | Demo rehearsal | ⏳ | |

## 4. What works right now
- `POST /query` with full 7-agent pipeline, parallel LLM calls, MLflow run per query.
- `GET /desert-map?min_total=30` aggregating capability gaps by state.
- `GET /health` smoke endpoint.
- Auto Swagger UI at `/docs`.
- Trust gap demonstrably working: "Find emergency surgery in rural Bihar" returns
  `Jindal Hospital And Endo Surgery Center` (anesthesiologist verified, trust 0.645)
  ranked above `Jalal Medical Center` (anesthesiologist uncertain, trust 0.235).

## 5. Cut order if we fall behind
1. /desert-map (drop first)
2. MLflow tracing (replace with simple JSON log)
3. Tavily LLM-validation layer (already replaced by `medical_rules.py` rule engine)
4. Lovable → fall back to Streamlit/Gradio in `backend/app.py` mount

## 6. Things the user needs to do
- [x] Provide OpenAI key
- [x] Provide Tavily key
- [ ] Sign up at https://huggingface.co (if not already)
- [ ] Generate an HF write token at https://huggingface.co/settings/tokens
- [ ] Create the Space at https://huggingface.co/new-space (Docker SDK, free CPU)
- [ ] Run `.\scripts\deploy_hf.ps1 -User <your-hf-username>`
- [ ] Add `OPENAI_API_KEY`, `TAVILY_API_KEY`, `CORS_ORIGINS` as Space secrets
- [ ] Get Lovable/v0 credits → run prompt from `docs/FRONTEND_PROMPT.md`
- [ ] Push generated frontend to GitHub → import to Vercel
- [ ] Set Vercel env `NEXT_PUBLIC_BACKEND_URL` to the Space URL
- [ ] **Rotate OpenAI + Tavily keys after the demo** (they were pasted in chat)

## 7. Eval criteria → how we score
| Criterion (weight) | Where it shows up |
|---|---|
| Discovery & Verification (35%) | ExtractionAgent's conservative `uncertain` policy + value normalizer; ValidatorAgent rule-engine + (optional) LLM cross-check; resumable batch with consistency hash |
| IDP Innovation (30%) | Hybrid retrieval (FAISS + structured filter); per-capability evidence sentence in response |
| Social Impact (25%) | `/desert-map` with PIN/state aggregation, configurable `min_total`, ready-to-render gap_ratio |
| UX & Transparency (10%) | TraceAgent reasoning per result + structured Trace + MLflow per-query run with metrics |

## 8. Known limitations (will note in demo)
- Demo runs on a 2,789-hospital subset (skips dentists/pharmacies).
  Full 10k extraction works but takes 75 min on free-tier rate limits.
- The dataset has some city names where `address_stateOrRegion` should be a state
  (e.g. "Aurangabad-bihar"); we surface the field as-is and let `min_total` filter
  hide the noise.
- `validator_agent.use_llm=False` by default to keep `/query` fast.
  Tavily standards still get cached on first use.
