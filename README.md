---
title: Healthmap Agent
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Agentic Healthcare Intelligence for India 10k facilities
---

# Healthmap Agent — Agentic Healthcare Intelligence System

Multi-agent system that turns the Virtue Foundation India 10k facility dataset into a **trust-aware** healthcare-discovery API. Built for the *Serving A Nation* hackathon (MIT Club of Northern California × Germany).

> Not a RAG demo. Each query is reasoned through 7 specialised agents, validated against external medical standards (Tavily), and scored for trustworthiness — with a full MLflow-traced reasoning chain.

## Why this matters
- **70% of India's population is rural** but most facility data is messy free-form text.
- Hospitals **claim capabilities they may not support** (e.g. "advanced surgery" with no anesthesiologist on staff).
- This system audits those claims at scale, flags contradictions, and returns ranked results with evidence.

## What it understands

The agent extracts and reasons over **11 capability tristates** plus doctor
employment type, covering both the MVP requirements and the high-acuity
specialties the brief calls out by name:

| Bucket | Capabilities |
|---|---|
| MVP | ICU, Emergency, Surgery, Anesthesiologist, Oxygen |
| High-acuity (brief callouts) | Oncology, Dialysis, Neonatal, Emergency Trauma |
| Supporting infrastructure | Lab, Imaging |
| Staffing | Full-time / Part-time / Unknown |

## The 7 agents
| # | Agent | Job |
|---|---|---|
| 1 | `query_agent` | NL query -> `{location, state, district, rural, required_capabilities, doctor_preference, constraints}` |
| 2 | `retrieval_agent` | FAISS vector search + structured filters |
| 3 | `extraction_agent` | Hospital notes -> conservative capability JSON (yes/no/uncertain) + verbatim evidence |
| 4 | `reasoning_agent` | Capability + doctor + (optional) Haversine proximity match |
| 5 | `validator_agent` | Rule engine for ALL candidates + LLM cross-check (Tavily standards) for top-K |
| 6 | `trust_agent` | Composite 0..1 trust score + warning flags |
| 7 | `trace_agent` | One-line per-result reasoning + structured trace |

Every step is logged as a single MLflow run per query, with a per-step
trace span (`@trace_step` -> `mlflow.trace` when available, no-op
otherwise) and a final cost summary (prompt tokens, completion tokens,
estimated USD).

## Quick start

```bash
# 1. clone + cd
git clone https://github.com/abdulahadalikhan12/healthmap-agent.git
cd healthmap-agent

# 2. env
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 3. secrets
cp .env.example .env            # then edit and add your keys

# 4. one-time data prep
python -m scripts.01_ingest                            # load xlsx -> parquet, build FAISS index
python -m scripts.02_extract_all --all --extractor hybrid  # extract ALL 10k rows cheaply

# 5. run API
uvicorn backend.app:app --reload --port 8000
```

### Full 10k extraction — choose your tradeoff

```bash
# Fastest + free: pure regex over all 10k rows (~30 s, $0.00)
python -m scripts.02_extract_all --all --extractor regex

# Best dollars-per-row: LLM on hospitals/clinics, regex elsewhere (~10 min, ~$0.65 on gpt-4o-mini)
python -m scripts.02_extract_all --all --extractor hybrid

# Maximum recall: LLM on every row (~75 min, ~$8 on gpt-4o-mini)
python -m scripts.02_extract_all --all --extractor llm

# Run the LLM path through Databricks Foundation Model serving (Agent Bricks):
# import databricks/notebooks/02b_extract_with_agent_bricks.py and run it.
```

Then `POST http://localhost:8000/query` with `{"query": "Find emergency surgery hospital in rural Bihar"}`.

## Project layout
```
backend/
  agents/        7 agent functions, one file each
  pipeline/      load, preprocess, embed, batch_extract, regex_extract
  core/          llm (multi-provider), tavily, prompts, schemas, mlflow_setup
  routers/       FastAPI routers (/query, /desert-map, /desert-map/pins)
  app.py         entrypoint
  orchestrator.py
scripts/         one-shot CLI scripts
databricks/
  notebooks/     00 setup, 01 ingest, 02 regex extract + trust + deserts,
                 02b Agent Bricks LLM extract, 03 query demo + MLflow trace,
                 04 Mosaic AI Vector Search (programmatic + sql template),
                 05 crisis map, 06 Genie space setup helper
  jobs/          pipeline_job.json -- multi-task Databricks job spec
docs/            DEPLOY, DEMO_QUERIES, FRONTEND_PROMPT, GENIE_PROMPTS,
                 DATABRICKS_RUNBOOK
data/            parquet + faiss + caches (gitignored)
dataset/         original xlsx (gitignored)
```

## Tech
- **Python 3.11+** (tested on 3.13.9)
- **Multi-provider LLM** via OpenAI-compatible client. Set `LLM_PROVIDER`
  to one of:
  | Provider     | Default model                                       | Embeddings   |
  |---           |---                                                  |---           |
  | `openai`     | `gpt-4o-mini`                                       | native       |
  | `databricks` | `databricks-meta-llama-3-1-70b-instruct` (Agent Bricks) | `databricks-bge-large-en` |
  | `groq`       | `llama-3.1-70b-versatile`                           | OpenAI fallback |
  | `together`   | `meta-llama/Llama-3.1-70B-Instruct-Turbo`           | `bge-base-en-v1.5` |
  | `fireworks`  | `accounts/fireworks/models/llama-v3p1-70b-instruct` | OpenAI fallback |
  | `openrouter` | `openai/gpt-4o-mini`                                | OpenAI fallback |
  | `huggingface`| TGI endpoint URL                                    | OpenAI fallback |
  | `custom`     | whatever you put in `OPENAI_*`                      | -            |
- **Retrieval**: FAISS (default, local) **or** Mosaic AI Vector Search
  (set `VECTOR_SEARCH_ENDPOINT` + `VECTOR_SEARCH_INDEX` to switch).
- **Tavily** for medical-standard web validation.
- **MLflow** for per-query traceability + token / USD cost tracking
  (`@trace_step` uses `mlflow.trace` when available, no-op otherwise).
- **FastAPI** for the HTTP API.
- **Hugging Face Spaces** (Docker SDK) for backend deploy.
- **Databricks notebooks** (`databricks/notebooks/00..06_*`) for the
  Databricks-native demo path (Delta + Agent Bricks + Mosaic AI VS + Genie).
- **Next.js UI** in `web/` for **Vercel** (or Lovable in a separate repo; same API contract in `docs/FRONTEND_PROMPT.md`).

## Deployment
Full guide: `docs/DEPLOY.md`. **TL;DR when you are exhausted:** (1) Push backend + data to HF with `scripts/deploy_hf.ps1`. (2) In Vercel, import this repo, **Root directory `web`**, set `NEXT_PUBLIC_BACKEND_URL` to your Space. (3) Add your Vercel URL to the Space’s `CORS_ORIGINS` secret and restart the Space.

## Status
See [`TASK.md`](./TASK.md) for the live build plan and progress.
