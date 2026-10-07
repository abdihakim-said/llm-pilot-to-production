"""Lending Policy Assistant API.

One request = redact -> screen -> retrieve -> generate (streamed), with release
metadata, Prometheus metrics and an MLflow trace for every answer.
"""

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from . import tracing
from .config import settings
from .retrieval import Retriever, load_chunks
from .safety import looks_like_injection, redact

log = logging.getLogger("assistant")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

REFUSAL_INJECTION = (
    "I can't help with that request. I only answer questions about the Northbridge "
    "lending policy manual, and I can't change or reveal my instructions."
)
NO_CONTEXT = "The policy manual doesn't cover this — please check with a Lending Manager."

REQUESTS = Counter("assistant_requests_total", "Chat requests", ["outcome", "track", "release"])
LATENCY = Histogram(
    "assistant_request_seconds", "End-to-end answer time", ["track", "release"],
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60),
)
TTFT = Histogram(
    "assistant_time_to_first_token_seconds", "Time to first streamed token", ["track", "release"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13),
)
REDACTIONS = Counter("assistant_redactions_total", "Personal data items redacted", ["type"])
TOKENS = Counter("assistant_completion_tokens_total", "Completion tokens generated", ["track", "release"])
FEEDBACK = Counter("assistant_feedback_total", "User feedback", ["value", "track", "release"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=20)
    stream: bool = True


class FeedbackRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=128)
    value: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


def current_track() -> str:
    """'stable' or 'canary', from labels Argo Rollouts puts on this pod."""
    try:
        for line in (settings.podinfo_dir / "labels").read_text().splitlines():
            key, _, value = line.partition("=")
            if key == "role":
                return value.strip('"')
    except OSError:
        pass
    return "stable"


class RateLimiter:
    """Per-user sliding window. Per pod; a shared store is the multi-replica upgrade."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, user: str) -> bool:
        now, window = time.monotonic(), self._hits[user]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.retriever = Retriever(load_chunks(settings.policy_dir))
    app.state.http = httpx.AsyncClient(base_url=settings.model_url, timeout=settings.model_timeout_s)
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    tracing.configure()
    log.info("release=%s prompt=%s model=%s chunks=%d", settings.release, settings.prompt_version,
             settings.model_name, len(app.state.retriever.chunks))
    yield
    await app.state.http.aclose()


app = FastAPI(title="Lending Policy Assistant API", version=settings.release, lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


def release_info() -> dict[str, str]:
    return {
        "release": settings.release,
        "prompt_version": settings.prompt_version,
        "model": settings.model_name,
        "track": current_track(),
    }


def validate(req: ChatRequest) -> None:
    """Checked before streaming starts, so clients get a proper 4xx."""
    if req.messages[-1].role != "user":
        raise HTTPException(422, "last message must be from the user")
    if len(req.messages[-1].content) > settings.max_input_chars:
        raise HTTPException(413, f"question longer than {settings.max_input_chars} characters")


async def run_chat(req: ChatRequest, user: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Core pipeline. Yields (event, data) pairs consumed by the SSE and JSON endpoints."""
    meta = release_info()
    labels = {"track": meta["track"], "release": meta["release"]}
    started = time.perf_counter()

    history = req.messages[:-1][-6:]
    clean = redact(req.messages[-1].content)
    for kind, n in clean.counts.items():
        REDACTIONS.labels(kind).inc(n)

    root = tracing.start("lending_assistant.chat", "CHAIN", inputs={"question": clean.text},
                         attributes={**meta, "user": user, "redactions": clean.total})
    trace_id = tracing.trace_id(root)
    base = {**meta, "trace_id": trace_id, "redactions": clean.counts}
    answer: list[str] = []
    outcome = "error"

    try:
        if looks_like_injection(clean.text):
            outcome = "blocked"
            yield "meta", {**base, "sources": [], "blocked": True}
            answer.append(REFUSAL_INJECTION)
            yield "token", {"t": REFUSAL_INJECTION}
        else:
            retr = tracing.start("retrieve_policy", "RETRIEVER", parent=root, inputs={"query": clean.text})
            chunks = app.state.retriever.search(clean.text, k=settings.retrieval_k)
            sources = [{"citation": c.citation, "doc": c.doc} for c in chunks]
            tracing.end(retr, outputs={"sources": sources})
            yield "meta", {**base, "sources": sources, "blocked": False}

            if not chunks:
                outcome = "no_context"
                answer.append(NO_CONTEXT)
                yield "token", {"t": NO_CONTEXT}
            else:
                async for token in generate(root, chunks, history, clean.text, labels, started):
                    answer.append(token)
                    yield "token", {"t": token}
                outcome = "ok"
    except httpx.HTTPError as exc:
        log.warning("model call failed: %s", exc)
        yield "error", {"message": "The assistant is temporarily unavailable. Please try again shortly."}
    finally:
        # No yields here: this also runs when the client disconnects mid-stream.
        elapsed = time.perf_counter() - started
        REQUESTS.labels(outcome=outcome, **labels).inc()
        LATENCY.labels(**labels).observe(elapsed)
        tracing.end(root, outputs={"answer": "".join(answer), "outcome": outcome},
                    status="ERROR" if outcome == "error" else "OK")

    yield "done", {"trace_id": trace_id, "latency_ms": round(elapsed * 1000), "outcome": outcome}


async def generate(root: Any, chunks: list, history: list[Message], question: str,
                   labels: dict[str, str], started: float) -> AsyncIterator[str]:
    context = "\n\n".join(f"[{c.citation}]\n{c.text}" for c in chunks)
    messages = [
        {"role": "system", "content": f"{settings.system_prompt}\n\nPolicy extracts:\n{context}"},
        *({"role": m.role, "content": redact(m.content).text} for m in history),
        {"role": "user", "content": question},
    ]
    span = tracing.start("generate", "CHAT_MODEL", parent=root,
                         inputs={"messages": messages}, attributes={"model": settings.model_name})
    parts: list[str] = []
    usage: dict[str, Any] = {}
    try:
        async with app.state.http.stream("POST", "/v1/chat/completions", json={
            "model": settings.model_name,
            "messages": messages,
            "max_tokens": settings.max_tokens,
            "temperature": settings.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    token = choice.get("delta", {}).get("content")
                    if token:
                        if not parts:
                            TTFT.labels(**labels).observe(time.perf_counter() - started)
                        parts.append(token)
                        yield token
    finally:
        TOKENS.labels(**labels).inc(usage.get("completion_tokens", 0))
        tracing.end(span, outputs={"answer": "".join(parts), "usage": usage})


def _identity(request: Request, x_user: str | None) -> str:
    user = x_user or "anonymous"
    if user not in settings.rate_limit_exempt and not app.state.limiter.allow(user):
        raise HTTPException(429, "Too many questions in the last minute. Please wait a moment.")
    return user


@app.post("/v1/chat")
async def chat(req: ChatRequest, request: Request, x_user: str | None = Header(default=None)):
    validate(req)
    user = _identity(request, x_user)
    events = run_chat(req, user)

    if not req.stream:
        answer, meta, done, error = [], {}, {}, None
        async for event, data in events:
            if event == "meta":
                meta = data
            elif event == "token":
                answer.append(data["t"])
            elif event == "error":
                error = data["message"]
            elif event == "done":
                done = data
        if error:
            return JSONResponse({"error": error, **done}, status_code=503)
        return {"answer": "".join(answer), "meta": meta, **done}

    async def sse() -> AsyncIterator[str]:
        async for event, data in events:
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/v1/feedback", status_code=202)
async def feedback(req: FeedbackRequest, x_user: str | None = Header(default=None)):
    info = release_info()
    FEEDBACK.labels(req.value, info["track"], info["release"]).inc()
    tracing.feedback(req.trace_id, req.value == "up", req.comment, x_user or "anonymous")
    return {"status": "recorded"}


@app.get("/v1/release")
async def release():
    return release_info()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    try:
        r = await app.state.http.get("/health", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, "model server not ready")
    return {"status": "ready", **release_info()}
