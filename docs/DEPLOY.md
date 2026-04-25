# Deploy guide

## Backend → Hugging Face Spaces (Docker)

### 1. Create the Space (one-time)

1. Go to https://huggingface.co/new-space
2. Owner: your account
3. Space name: `healthmap-agent`
4. License: MIT
5. **SDK: Docker**
6. **Hardware: CPU basic (free)**
7. Visibility: Public
8. Click **Create Space**

### 2. Add Space secrets (one-time)

In the Space → **Settings → Variables and secrets**, add:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key |
| `TAVILY_API_KEY` | your Tavily key |
| `CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app,http://localhost:3000` |

### 3. Push the code

The Space is itself a git repo. We push the same files we have locally,
but the Space repo expects an `app/` Docker entrypoint as the project root.

From the project root:

```powershell
# add the HF Space as an additional git remote
git remote add hf https://huggingface.co/spaces/<your-username>/healthmap-agent

# push (use your HF user-access token as the password when prompted)
git push hf main
```

Generate an HF token at https://huggingface.co/settings/tokens (scope: write).

### 4. About data files

The FAISS index (`data/index/`), the canonical parquet (`data/processed/`),
and the extracted capabilities parquet (`data/extracted/`) are gitignored
locally so they don't bloat your GitHub repo. But the Docker image needs
them.

Two options:

**Option A — bake them into the image (simplest, works now):**

Temporarily relax the gitignore for the HF push only:

```powershell
git push hf main --force-with-lease
# then on the HF Space repo, manually upload the data/ folder via the web UI
```

OR check `data/processed/`, `data/index/`, `data/extracted/` into the
HF-only branch:

```powershell
git checkout -b hf-deploy
# copy a temporary .gitignore that doesn't ignore data/
git add data/
git commit -m "deploy: include built artifacts"
git push hf hf-deploy:main --force
git checkout main
```

**Option B — rebuild on first boot (slower, but cleaner):**

Add an entrypoint that runs `python -m scripts.01_ingest && python -m scripts.02_extract_all`
on container start. This requires uploading the raw `dataset/*.xlsx` to
the Space (use the HF web UI **Files → Upload file**, or git-LFS).

For the hackathon I recommend **Option A** — fewer moving parts.

### 5. Test

After the Space builds (~3 min), curl it:

```powershell
curl -X POST https://<your-username>-healthmap-agent.hf.space/query `
     -H "Content-Type: application/json" `
     -d '{"query":"Find emergency surgery hospital in rural Bihar"}'
```

## Frontend → Vercel

1. Lovable / v0 produces a Next.js project.
2. Push it to a GitHub repo (e.g. `healthmap-frontend`).
3. Import to Vercel.
4. Set env var `NEXT_PUBLIC_BACKEND_URL=https://<your-username>-healthmap-agent.hf.space`.
5. Deploy.
6. Add the Vercel URL to your Space's `CORS_ORIGINS`.
