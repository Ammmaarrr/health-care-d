"""Centralized settings loaded from .env.

Multi-provider LLM support: set `LLM_PROVIDER` to one of

    openai      (default; uses OPENAI_API_KEY)
    databricks  (Databricks Foundation Model serving / Agent Bricks)
    groq        (Groq's OpenAI-compatible endpoint)
    together    (Together AI)
    fireworks   (Fireworks AI)
    openrouter  (OpenRouter aggregator)
    huggingface (HF inference endpoints, OpenAI-compatible)
    custom      (use OPENAI_BASE_URL verbatim)

Each profile fills sensible defaults for `OPENAI_BASE_URL`,
`OPENAI_LLM_MODEL`, and `OPENAI_EMBED_MODEL` if those are not set
explicitly. Pricing for cost tracking lives in `backend.core.llm`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# Provider-specific defaults. None means "fall back to whatever the user
# put in the env vars". Embeddings: not every provider serves them; we
# fall back to OpenAI for embeddings unless the user overrides.
_PROVIDER_PROFILES: dict[str, dict[str, str | None]] = {
    "openai": {
        "base_url": None,  # SDK default
        "llm_model": "gpt-4o-mini",
        "embed_model": "text-embedding-3-small",
    },
    "databricks": {
        "base_url": None,  # filled at runtime from DATABRICKS_HOST
        "llm_model": "databricks-meta-llama-3-1-70b-instruct",
        "embed_model": "databricks-bge-large-en",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "llm_model": "llama-3.1-70b-versatile",
        "embed_model": None,  # Groq does not currently serve embeddings
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "llm_model": "meta-llama/Llama-3.1-70B-Instruct-Turbo",
        "embed_model": "BAAI/bge-base-en-v1.5",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "llm_model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "embed_model": None,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "llm_model": "openai/gpt-4o-mini",
        "embed_model": None,
    },
    "huggingface": {
        "base_url": None,  # user supplies the inference endpoint URL
        "llm_model": "tgi",
        "embed_model": None,
    },
    "custom": {
        "base_url": None,
        "llm_model": None,
        "embed_model": None,
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider switch --- #
    llm_provider: str = "openai"

    openai_api_key: str = ""
    openai_llm_model: str = ""           # "" -> use provider default
    openai_embed_model: str = ""         # "" -> use provider default / fallback to OpenAI
    openai_base_url: str | None = None   # "" / None -> use provider default

    # Databricks-specific (only used when llm_provider == "databricks")
    databricks_host: str = ""            # e.g. https://dbc-xxx.cloud.databricks.com
    databricks_token: str = ""           # PAT or OAuth M2M token
    databricks_llm_endpoint: str = ""    # serving endpoint name; falls back to provider default
    databricks_embed_endpoint: str = ""

    # Mosaic AI Vector Search (optional retrieval backend)
    vector_search_endpoint: str = ""
    vector_search_index: str = ""        # full name: catalog.schema.index_name

    tavily_api_key: str = ""

    data_raw_path: str = "dataset/VF_Hackathon_Dataset_India_Large.xlsx"
    data_dir: str = "data"

    extraction_sample_size: int = 1000
    # When llm_provider unsupports embeddings, fall back to OpenAI.
    embed_fallback_to_openai: bool = True

    mlflow_tracking_uri: str = "./mlruns"
    mlflow_experiment_name: str = "healthmap-agent"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ----- Resolved provider profile (memoised lazily on first access) ----- #
    def _profile(self) -> dict[str, str | None]:
        return _PROVIDER_PROFILES.get(self.llm_provider.lower(), _PROVIDER_PROFILES["openai"])

    @property
    def resolved_base_url(self) -> str | None:
        """Final base_url for the OpenAI-compatible client."""
        if self.openai_base_url:
            return self.openai_base_url
        prof = self._profile()
        if prof["base_url"]:
            return prof["base_url"]
        if self.llm_provider.lower() == "databricks" and self.databricks_host:
            return f"{self.databricks_host.rstrip('/')}/serving-endpoints"
        return None  # OpenAI SDK default

    @property
    def resolved_api_key(self) -> str:
        if self.llm_provider.lower() == "databricks" and self.databricks_token:
            return self.databricks_token
        return self.openai_api_key

    @property
    def resolved_llm_model(self) -> str:
        if self.openai_llm_model:
            return self.openai_llm_model
        prof = self._profile()
        if self.llm_provider.lower() == "databricks" and self.databricks_llm_endpoint:
            return self.databricks_llm_endpoint
        return prof["llm_model"] or "gpt-4o-mini"

    @property
    def resolved_embed_model(self) -> str:
        if self.openai_embed_model:
            return self.openai_embed_model
        prof = self._profile()
        if self.llm_provider.lower() == "databricks" and self.databricks_embed_endpoint:
            return self.databricks_embed_endpoint
        return prof["embed_model"] or "text-embedding-3-small"

    @property
    def embed_provider(self) -> str:
        """Which provider to use for embeddings.

        Returns one of: same as `llm_provider`, or "openai" when the
        configured provider can't serve embeddings and the fallback is
        enabled. "openai" implies a separate OPENAI_API_KEY must exist.
        """
        prof = self._profile()
        if prof["embed_model"] is None and self.embed_fallback_to_openai:
            return "openai"
        return self.llm_provider.lower()

    @property
    def data_root(self) -> Path:
        return PROJECT_ROOT / self.data_dir

    @property
    def raw_path(self) -> Path:
        return PROJECT_ROOT / self.data_raw_path

    @property
    def processed_path(self) -> Path:
        return self.data_root / "processed" / "hospitals.parquet"

    @property
    def index_path(self) -> Path:
        return self.data_root / "index" / "faiss.index"

    @property
    def index_meta_path(self) -> Path:
        return self.data_root / "index" / "faiss_meta.parquet"

    @property
    def extractions_path(self) -> Path:
        return self.data_root / "extracted" / "capabilities.parquet"

    @property
    def tavily_cache_dir(self) -> Path:
        return self.data_root / "tavily_cache"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
