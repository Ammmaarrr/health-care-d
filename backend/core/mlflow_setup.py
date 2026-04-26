"""MLflow setup helpers.

We log one MLflow run per `/query` call. The orchestrator wraps everything
in `mlflow.start_run(...)` and uses helpers here to log stages.

`trace_step(name)` is a decorator that wraps a function as an MLflow
trace span when MLflow exposes the tracing API (>= 2.14 / 3.x). On older
runtimes it is a no-op so the FastAPI service stays portable. This is
the same fallback strategy used in the Databricks notebooks.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, TypeVar

import mlflow

from backend.config import settings


_initialized = False
_F = TypeVar("_F", bound=Callable[..., Any])


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


def log_metrics(metrics: dict[str, float]) -> None:
    for k, v in metrics.items():
        try:
            log_metric(k, float(v))
        except Exception:
            continue


def log_genai_style_trace(
    *,
    query: str,
    steps: list[str],
    result_summary: dict,
) -> None:
    """Structured trace for MLflow UI (span-like tree) + compatibility hooks.

    MLflow 2.14+ exposes experiment traces; we always persist a full JSON
    artifact so runs remain inspectable even on older tracking servers.
    """
    tree = {
        "type": "agent_run",
        "query": query[:500],
        "spans": [{"name": f"step_{i+1}", "output": s} for i, s in enumerate(steps)],
        "result": result_summary,
    }
    log_step("agent_traceability_tree", tree)
    try:
        for i, s in enumerate(steps):
            mlflow.log_text(s, f"traces/span_{i+1:02d}.txt")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Tracing decorator (mirrors the Databricks notebook fallback)
# --------------------------------------------------------------------------- #
def _resolve_trace_decorator():
    """Return `mlflow.trace` if it exists *and* works, else None.

    MLflow 3 exposes `mlflow.trace`. MLflow 2.14+ has `mlflow.tracing`
    but the public decorator name varies; we probe at import time so the
    rest of the code can stay simple.
    """
    candidate = getattr(mlflow, "trace", None)
    if candidate is None:
        return None
    try:
        @candidate
        def _probe():
            return None

        _probe()
        return candidate
    except Exception:
        return None


_trace = _resolve_trace_decorator()


def trace_step(name: str | None = None) -> Callable[[_F], _F]:
    """Wrap a function as an MLflow trace span when supported.

    Usage::

        @trace_step("01_parse_query")
        def parse_query(...): ...

    On runtimes without `mlflow.trace` this is an identity decorator,
    so the agents still work and just lose the per-step span tree.
    """
    def decorator(fn: _F) -> _F:
        if _trace is None:
            return fn
        try:
            wrapped = _trace(fn) if name is None else _trace(name=name)(fn)
        except TypeError:
            wrapped = _trace(fn)

        # Preserve metadata.
        @wraps(fn)
        def _proxy(*args: Any, **kwargs: Any) -> Any:
            return wrapped(*args, **kwargs)

        return _proxy  # type: ignore[return-value]

    return decorator
