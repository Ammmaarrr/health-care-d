"""Centralized settings loaded from .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    # Optional override for OpenAI-compatible providers (Groq, Together, etc.)
    openai_base_url: str | None = None

    tavily_api_key: str = ""

    data_raw_path: str = "dataset/VF_Hackathon_Dataset_India_Large.xlsx"
    data_dir: str = "data"

    extraction_sample_size: int = 1000

    mlflow_tracking_uri: str = "./mlruns"
    mlflow_experiment_name: str = "healthmap-agent"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

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
