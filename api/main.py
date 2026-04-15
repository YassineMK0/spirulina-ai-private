"""SpirulinaAI FastAPI backend.

Start:
    .venv\\Scripts\\uvicorn api.main:app --reload --port 8000

Endpoints:
    POST   /chat                -> invoke LangGraph pipeline, return AI response
    GET    /history/{user_id}   -> return stored chat history for a user
    DELETE /history/{user_id}   -> clear chat history for a user
    GET    /health              -> liveness check
    GET    /alerts/{user_id}    -> SSE stream of proactive container alerts
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()


# ---------------------------------------------------------------------------
# Startup pre-warm — runs once when uvicorn starts, before first request
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SSE alert queues — one asyncio.Queue per connected user
# ---------------------------------------------------------------------------

_alert_queues: dict[str, asyncio.Queue] = {}
_event_loop = None   # captured at startup — used by scheduler thread to push alerts


def _push_alert(user_id: str, alert_text: str) -> None:
    """Push an alert into the user's SSE queue (called from scheduler thread)."""
    q = _alert_queues.get(user_id)
    if q and _event_loop:
        _event_loop.call_soon_threadsafe(q.put_nowait, alert_text)
        print(f"[monitor] alert pushed to {user_id}: {alert_text[:60]}...")
    else:
        print(f"[monitor] no SSE listener for {user_id} (queue={q is not None}, loop={_event_loop is not None})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    print("[startup] pre-warming graph + retriever...")
    try:
        from agent.graph import graph as _g
        global _graph
        _graph = _g
        print("[startup] graph compiled")
    except Exception as e:
        print(f"[startup] graph failed: {e}")

    try:
        from rag.retriever.retrieve import _get_collection, _get_bm25_index
        _get_collection()
        _get_bm25_index(None, None)
        print("[startup] retriever ready")
    except Exception as e:
        print(f"[startup] retriever failed: {e}")

    try:
        from api.predict_anomaly import load_artifacts
        load_artifacts()
        print("[startup] anomaly model ready")
    except Exception as e:
        print(f"[startup] anomaly model: {e}")

    # Start APScheduler — monitor fires every 5 minutes 
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from agent.monitor import run_monitor_check

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            lambda: run_monitor_check(_push_alert),
            "interval",
            seconds=30,
            id="container_monitor",
        )
        scheduler.start()
        print("[startup] monitor scheduler started (every 5 min)")
    except Exception as e:
        print(f"[startup] scheduler failed: {e}")

    print("[startup] ready — first message will be fast")
    yield  # app runs here

    # Shutdown scheduler cleanly
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(title="SpirulinaAI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Graph singleton
# ---------------------------------------------------------------------------

_graph = None

def _get_graph():
    global _graph
    if _graph is None:
        from agent.graph import graph
        _graph = graph
    return _graph


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message:      str
    user_id:      str = "anonymous"
    container_id: str = ""


class ChatResponse(BaseModel):
    response:   str
    intent:     str   = ""
    confidence: float = 0.0


class HistoryMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    from agent.memory import memory_store
    from agent.monitor import register_session

    # Track active session for proactive monitoring
    register_session(req.user_id, req.container_id)

    # Load history from Redis, append new user message
    history = memory_store.get(req.user_id)
    history.append({"role": "user", "content": req.message})

    result = _get_graph().invoke({
        "user_id":      req.user_id,
        "container_id": req.container_id,
        "chat_history": history,
    })

    response   = result.get("response", "Sorry, something went wrong.")
    intent     = result.get("intent",    "")
    confidence = result.get("confidence", 0.0)

    # Save updated history back to Redis (auto-capped at 10 turns)
    history.append({"role": "assistant", "content": response})
    memory_store.save(req.user_id, history)

    return ChatResponse(response=response, intent=intent, confidence=confidence)


@app.get("/alerts/{user_id}")
async def alerts_sse(user_id: str):
    """Server-Sent Events stream — pushes proactive alerts to the browser."""
    q: asyncio.Queue = asyncio.Queue()
    _alert_queues[user_id] = q

    async def event_stream():
        try:
            # Send a heartbeat immediately so the browser knows the stream is open
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                try:
                    alert_text = await asyncio.wait_for(q.get(), timeout=30.0)
                    payload = json.dumps({"type": "alert", "text": alert_text})
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment every 30s to prevent connection drop
                    yield ": keepalive\n\n"
        finally:
            _alert_queues.pop(user_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history/{user_id}", response_model=list[HistoryMessage])
def get_history(user_id: str):
    """Return the stored chat history for a user (for rendering on page load)."""
    from agent.memory import memory_store
    return memory_store.get(user_id)


@app.delete("/history/{user_id}")
def clear_history(user_id: str):
    """Wipe the chat history for a user."""
    from agent.memory import memory_store
    memory_store.clear(user_id)
    return {"status": "cleared"}
