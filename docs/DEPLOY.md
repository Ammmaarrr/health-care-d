# Deploy guide

Backend → **Hugging Face Spaces (Docker)**, frontend → **Vercel**.

---

## Backend on HF Spaces

### 1. Create the Space (one-time)
1. Go to https://huggingface.co/new-space
2. Owner: your account
3. Name: `healthmap-agent`
4. License: MIT
5. **SDK: Docker** (do not pick Streamlit/Gradio)
6. **Hardware: CPU basic (free)**
7. Visibility: Public
8. Click **Create Space**

The newly-created Space is just a git repo at `https://huggingface.co/spaces/<you>/healthmap-agent`.

### 2. Generate a write token
- https://huggingface.co/settings/tokens → **Create new token** → role **write** → copy.

### 3. Add Space secrets (one-time)
In the Space → **Settings → Variables and secrets**, click **New secret** and add:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key |
| `TAVILY_API_KEY` | your Tavily key |
| `CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app,http://localhost:3000` |

### 4. Push the code (with data)
The Space needs the code **plus** the built FAISS index + parquet artefacts
to start fast. We use a helper script that builds a deploy branch
including those files (which are gitignored on GitHub).

From the project root in PowerShell:
```powershell
.\scripts\deploy_hf.ps1 -User <your-hf-username>
```

You'll be prompted for username + password — paste your HF write token
as the password. The script:

1. Adds the HF Space as a `hf` git remote (idempotent).
2. Creates a temporary `hf-deploy` branch and force-adds `data/processed`,
   `data/index`, `data/extracted`.
3. Force-pushes `hf-deploy → main` on the Space.
4. Returns you to your original branch.

The Space starts building automatically. First build takes ~3 min.

### 5. Verify
```powershell
curl https://<your-hf-username>-healthmap-agent.hf.space/health
# {"ok":true}

curl -X POST https://<your-hf-username>-healthmap-agent.hf.space/query `
     -H "Content-Type: application/json" `
     -d '{"query":"Find emergency surgery hospital in rural Bihar"}'

# Crisis map (PIN-level zones) — must return JSON with a `zones` array.
curl "https://<your-hf-username>-healthmap-agent.hf.space/desert-map/pins?capability=icu&top=5"
```

If the frontend crisis map shows **404** for every capability, the Space is still running an **older image** that predates `/desert-map/pins`. GitHub `main` can be up to date while the Space lags: the Space is updated by **`scripts\deploy_hf.ps1`**, not by `git push origin` alone. Re-run the deploy script (step 4), wait for the build to finish, then hit the `desert-map/pins` URL again.

If `/health` works but `/query` returns 503, the Space hasn't received
the data yet — re-run `scripts\deploy_hf.ps1`.

### 6. Re-deploy
Just run `scripts\deploy_hf.ps1` again whenever you push code or
rebuild the cache.

---

## Frontend on Vercel

The API (FAISS, long requests) stays on **Hugging Face Spaces**. Vercel hosts
only the **Next.js** UI in this repo under `web/` (same contract as
`docs/FRONTEND_PROMPT.md`).

### Option A — this monorepo (`web/`)

1. Push the repo to GitHub (or use the existing `health-care-d` remote).
2. [vercel.com/new](https://vercel.com/new) → **Import** the repository.
3. **Root Directory:** set to `web` (Project Settings → General, or during import “Override”).
4. **Environment variables** (Production + Preview):
   - `NEXT_PUBLIC_BACKEND_URL` = `https://<your-hf-username>-<space-name>.hf.space`  
     (no trailing slash; use your real Space URL from Hugging Face).
5. **Deploy.** Vercel runs `npm install` and `npm run build` inside `web/`.
6. Copy the deployment URL (e.g. `https://health-care-d.vercel.app`) and add it
   to the Space’s **`CORS_ORIGINS`** (comma-separated with
   `http://localhost:3000` if you still test locally), then **Restart** the Space
   or re-run `scripts/set_hf_secrets.py` with `--cors-origins`.

Local preview (requires Node 18+ / npm on your machine):

```powershell
cd web
Copy-Item .env.example .env.local   # set NEXT_PUBLIC_BACKEND_URL
npm install
npm run dev
```

### Option B — separate Lovable / v0 project

1. Generate the UI with `docs/FRONTEND_PROMPT.md` and push that Next.js app to
   its own GitHub repo.
2. Import that repo in Vercel, set the same `NEXT_PUBLIC_BACKEND_URL`, and
   update `CORS_ORIGINS` on the Space as in step 6 above.

---

## Local dev (no deploy)

```powershell
.\.venv\Scripts\activate
uvicorn backend.app:app --reload --port 8000
```

Hit http://localhost:8000/docs for the interactive Swagger UI.

---

## Switching the LLM provider

Set `LLM_PROVIDER` in `.env` (or as a Space secret) to one of:

```text
openai (default), databricks, groq, together, fireworks,
openrouter, huggingface, custom
```

Each profile fills sensible defaults for `OPENAI_BASE_URL`,
`OPENAI_LLM_MODEL`, and `OPENAI_EMBED_MODEL` from
`backend/config.py::_PROVIDER_PROFILES`. Override any of those env vars
to take control. Token cost tracking adapts automatically (see
`backend/core/llm.py::_PRICE_PER_M_PROMPT_USD` / `_COMPLETION_USD`).

Example — Databricks Agent Bricks:

```text
LLM_PROVIDER=databricks
DATABRICKS_HOST=https://dbc-xxxxxxx-xxxx.cloud.databricks.com
DATABRICKS_TOKEN=<PAT>
DATABRICKS_LLM_ENDPOINT=databricks-meta-llama-3-1-70b-instruct
DATABRICKS_EMBED_ENDPOINT=databricks-bge-large-en
```

Example — Groq (free tier, OpenAI fallback for embeddings):

```text
LLM_PROVIDER=groq
OPENAI_API_KEY=<groq key>
EMBED_FALLBACK_TO_OPENAI=true
# also keep your real OPENAI_API_KEY around so embeddings still work
```

---

## Switching to Mosaic AI Vector Search

1. In Databricks: import and run `databricks/notebooks/04_vector_search.py`.
   It creates the endpoint, index, and the smoke test.
2. In `.env` (or Space secrets):
   ```text
   VECTOR_SEARCH_ENDPOINT=healthmap-vector-search
   VECTOR_SEARCH_INDEX=workspace.healthmap_agent.facilities_clean_vs_index
   DATABRICKS_HOST=https://...
   DATABRICKS_TOKEN=...
   ```
3. Install the optional SDK on your backend host:
   ```bash
   pip install databricks-vectorsearch
   ```
4. The retriever auto-detects the env vars and routes through Mosaic
   AI VS. If the call fails it falls back to the local FAISS index, so
   the API never goes down.

---

## Running the full Databricks pipeline as a job

```powershell
databricks jobs create --json @databricks/jobs/pipeline_job.json
```

The pipeline runs setup -> ingest -> regex extract / trust / deserts ->
crisis map -> Genie setup helper. To swap regex for LLM extraction, add
the `extract_with_agent_bricks` task pointing at `02b_extract_with_agent_bricks`
and update notebook 02 / 03 to read from `capabilities_extracted_llm`
(see `docs/DATABRICKS_RUNBOOK.md`).
