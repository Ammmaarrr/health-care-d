# Dockerfile for Hugging Face Spaces (Docker SDK).
#
# HF Spaces runs containers as a non-root user (uid 1000). Anything the
# app writes at runtime (FAISS index, MLflow runs, Tavily cache) must go
# under a writable path. We use /home/user/app/data (mounted writable).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# Create the HF-style non-root user.
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Install deps first (better layer caching).
COPY --chown=user:user requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the app.
COPY --chown=user:user backend ./backend
COPY --chown=user:user scripts ./scripts
# `dataset/` and `data/` should be uploaded to the Space directly,
# OR built once on first boot via an entrypoint script. For the
# hackathon, we ship the parquet + faiss index inside the image
# via the .gitattributes / Space repo (see DEPLOY.md).
COPY --chown=user:user data ./data

USER user

EXPOSE 7860

# HF Spaces routes traffic to PORT 7860.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
