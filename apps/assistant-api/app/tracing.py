"""Thin MLflow 3 tracing wrapper.

Tracing must never break answering: if MLflow is unset or down, every call
here is a no-op. Spans use the no-context API because they cross the yields
of a streaming generator.
"""

import logging
import os
import threading
import time
from typing import Any

from .config import settings

log = logging.getLogger("assistant.tracing")
_enabled = False


def configure() -> None:
    """Connect to MLflow in the background so startup never waits on it."""
    if not settings.mlflow_tracking_uri:
        log.info("MLflow tracing disabled (no tracking URI)")
        return
    os.environ.setdefault("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "true")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
    threading.Thread(target=_connect, name="mlflow-connect", daemon=True).start()


def _connect(retry_s: float = 30.0) -> None:
    global _enabled
    while not _enabled:
        try:
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow.set_experiment(settings.mlflow_experiment)
            _enabled = True
            log.info("MLflow tracing to %s", settings.mlflow_tracking_uri)
        except Exception as exc:  # noqa: BLE001 - tracing is best-effort
            log.warning("MLflow unavailable, retrying in %ss: %s", retry_s, exc)
            time.sleep(retry_s)


def start(name: str, span_type: str, parent: Any = None, inputs: Any = None,
          attributes: dict[str, Any] | None = None) -> Any:
    if not _enabled:
        return None
    try:
        import mlflow

        kwargs: dict[str, Any] = {}
        if parent is None and attributes:
            kwargs["tags"] = {k: str(v) for k, v in attributes.items() if k in ("release", "prompt_version", "track")}
            kwargs["metadata"] = {"mlflow.trace.user": str(attributes.get("user", "anonymous"))}
        return mlflow.start_span_no_context(
            name=name, span_type=span_type, parent_span=parent, inputs=inputs,
            attributes={k: str(v) for k, v in (attributes or {}).items()}, **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("span start failed: %s", exc)
        return None


def end(span: Any, outputs: Any = None, status: str = "OK") -> None:
    if span is None:
        return
    try:
        span.end(outputs=outputs, status=status)
    except Exception as exc:  # noqa: BLE001
        log.warning("span end failed: %s", exc)


def trace_id(span: Any) -> str | None:
    return getattr(span, "trace_id", None) if span is not None else None


def feedback(trace: str, positive: bool, comment: str | None, user: str) -> None:
    if not _enabled:
        return
    try:
        import mlflow
        from mlflow.entities import AssessmentSource

        mlflow.log_feedback(
            trace_id=trace, name="user_feedback", value=positive, rationale=comment,
            source=AssessmentSource(source_type="HUMAN", source_id=user),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("feedback logging failed: %s", exc)
