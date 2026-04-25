"""MLflow setup helpers.

We log one MLflow run per `/query` call. The orchestrator wraps everything
in `mlflow.start_run(...)` and uses helpers here to log stages.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

import mlflow

from backend.config import settings


_initialized = False


def init() -> None:
    global _initialized
    if _initialized:
        return
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)
    _initialized = True


@contextmanager
def query_run(query: str) -> Iterator[None]:
    init()
    with mlflow.start_run(run_name=f"query: {query[:60]}"):
        mlflow.log_param("query", query)
        yield


def log_step(name: str, payload: Any) -> None:
    """Log a JSON-serialisable payload as an artifact under stage name."""
    try:
        text = json.dumps(payload, default=str, indent=2)
    except TypeError:
        text = str(payload)
    mlflow.log_text(text, f"steps/{name}.json")


def log_metric(name: str, value: float) -> None:
    try:
        mlflow.log_metric(name, float(value))
    except Exception:
        pass
