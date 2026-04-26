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

1. Generate the UI (Lovable or v0) using `docs/FRONTEND_PROMPT.md`.
2. Push the generated Next.js project to a GitHub repo (e.g.
   `healthmap-frontend`).
3. https://vercel.com/new → import the repo.
4. Set env var: `NEXT_PUBLIC_BACKEND_URL=https://<your-hf-username>-healthmap-agent.hf.space`.
5. Deploy.
6. Copy the Vercel URL (e.g. `https://healthmap-agent.vercel.app`)
   and add it to the Space's `CORS_ORIGINS` secret. The Space will
   restart automatically.

---

## Local dev (no deploy)

```powershell
.\.venv\Scripts\activate
uvicorn backend.app:app --reload --port 8000
```

Hit http://localhost:8000/docs for the interactive Swagger UI.
