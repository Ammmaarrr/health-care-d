# Healthmap Agent — Agentic Healthcare Intelligence System

Multi-agent system that turns the Virtue Foundation India 10k facility dataset into a **trust-aware** healthcare-discovery API. Built for the *Serving A Nation* hackathon (MIT Club of Northern California × Germany).

> Not a RAG demo. Each query is reasoned through 7 specialised agents, validated against external medical standards (Tavily), and scored for trustworthiness — with a full MLflow-traced reasoning chain.

## Why this matters
- **70% of India's population is rural** but most facility data is messy free-form text.
- Hospitals **claim capabilities they may not support** (e.g. "advanced surgery" with no anesthesiologist on staff).
- This system audits those claims at scale, flags contradictions, and returns ranked results with evidence.

## The 7 agents
| # | Agent | Job |
|---|---|---|
| 1 | `query_agent` | NL query → `{location, capabilities, constraints}` |
| 2 | `retrieval_agent` | FAISS vector search + structured filters |
| 3 | `extraction_agent` | Hospital notes → conservative capability JSON (yes/no/uncertain) |
| 4 | `reasoning_agent` | Match against query, rank, never assume missing data |
| 5 | `validator_agent` | Cross-check against Tavily-fetched medical standards + rule engine |
| 6 | `trust_agent` | Composite 0–1 trust score + warning flags |
| 7 | `trace_agent` | Human-readable explanation of every decision |

All steps are logged as a single MLflow run per query.

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
python -m scripts.01_ingest          # load xlsx -> parquet, build FAISS index
python -m scripts.02_extract_all     # batch extract capabilities (sample of 1000 by default)

# 5. run API
uvicorn backend.app:app --reload --port 8000
```

Then `POST http://localhost:8000/query` with `{"query": "Find emergency surgery hospital in rural Bihar"}`.

## Project layout
```
backend/
  agents/       7 agent functions, one file each
  pipeline/     load, preprocess, embed, batch_extract
  core/         llm, tavily, prompts, schemas, mlflow_setup
  routers/      FastAPI routers
  app.py        entrypoint
  orchestrator.py
scripts/        one-shot CLI scripts
data/           parquet + faiss + caches (gitignored)
dataset/        original xlsx (gitignored)
notebooks/      exploration
```

## Tech
- **Python 3.11+** (tested on 3.13.9)
- **OpenAI** `gpt-4o-mini` for reasoning, `text-embedding-3-small` for vectors
- **FAISS** for retrieval
- **Tavily** for medical-standard web validation
- **MLflow** for per-query traceability (Stretch Goal #1 in the brief)
- **FastAPI** for the API
- **Hugging Face Spaces** (Docker SDK) for backend deploy
- **Lovable / v0 → Vercel** for frontend

## Deployment
See `docs/DEPLOY.md` (will be added during step 8 of the plan).

## Status
See [`TASK.md`](./TASK.md) for the live build plan and progress.
