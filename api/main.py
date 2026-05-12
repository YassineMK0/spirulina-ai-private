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

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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


def _background_warmup():
    """Load bge-m3, BM25 index, and ML models in a background thread.

    Runs after uvicorn is already accepting requests so the server is
    immediately available.  First /chat request before this finishes will
    trigger an on-demand load (slightly slower, but still works).
    """
    try:
        from rag.retriever.retrieve import _get_collection, _get_bm25_index
        _get_collection()
        _get_bm25_index(None, None)
        print("[warmup] bge-m3 + BM25 ready")
    except Exception as e:
        print(f"[warmup] retriever failed: {e}")

    try:
        from api.predict_lstm import load_artifact as load_m1
        load_m1()
        print("[warmup] M1 LSTM ready")
    except Exception as e:
        print(f"[warmup] M1 LSTM: {e}")

    try:
        from api.predict_lgbm import load_artifact as load_m2
        load_m2()
        print("[warmup] M2 LightGBM turbidity ready")
    except Exception as e:
        print(f"[warmup] M2 LightGBM: {e}")

    try:
        from api.predict_lgbm_harvest import load_artifacts as load_m3
        load_m3()
        print("[warmup] M3 LightGBM harvest ready")
    except Exception as e:
        print(f"[warmup] M3 LightGBM harvest: {e}")

    print("[warmup] all models loaded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    global _event_loop
    _event_loop = asyncio.get_event_loop()

    # Compile graph synchronously — fast, no model loading
    try:
        from agent.graph import graph as _g
        global _graph
        _graph = _g
        print("[startup] graph compiled")
    except Exception as e:
        print(f"[startup] graph failed: {e}")

    # bge-m3 + ML models in background — server accepts requests immediately
    threading.Thread(target=_background_warmup, daemon=True, name="warmup").start()
    print("[startup] ready — bge-m3 loading in background (first request may be slow)")

    try:
        from agent.sensors import start_mqtt_subscriber
        start_mqtt_subscriber()
        print("[startup] MQTT subscriber started")
    except Exception as e:
        print(f"[startup] MQTT subscriber: {e}")

    # Start APScheduler — monitor fires every 5 minutes 
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from agent.monitor import run_monitor_check

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            lambda: run_monitor_check(_push_alert),
            "interval",
            seconds=15,
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
    user_id:      str  = "anonymous"
    container_id: str  = ""
    tier:         str  = "free"   # "free" | "pro"


class ChatResponse(BaseModel):
    response:   str
    content:    dict  = {}        # structured content for Next.js renderer
    tools_used: list  = []        # tool pill labels shown in the UI
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


@app.get("/models/{container_id}")
def get_model_outputs(container_id: str):
    """Run M1/M2/M3 on latest sensor history and return live outputs."""
    import numpy as np
    import pandas as pd
    from agent.sensors import get_history

    history = get_history(container_id)
    if not history:
        return JSONResponse(
            content={"error": "no_data"},
            headers={"Cache-Control": "no-store"},
        )

    df     = pd.DataFrame(history)
    result = {"m1": {}, "m2": {}, "m3": {}, "readings": len(history)}

    try:
        from api.predict_lstm import predict_df, load_artifact as load_m1
        out  = predict_df(df, load_m1())
        last = out.iloc[-1]
        score = float(last["anomaly_score"]) if not np.isnan(last["anomaly_score"]) else 0.0
        result["m1"] = {
            "anomaly":  bool(last["is_anomaly"]),
            "score":    round(score, 4),
            "severity": str(last["severity"]),
            "trend":    str(last["trend_direction"]),
        }
    except Exception as exc:
        result["m1"] = {"error": str(exc)}

    try:
        from api.predict_lgbm import predict, load_artifact as load_m2
        out = predict(df, load_m2())
        result["m2"] = {
            "low":        round(out["low"], 1),
            "prediction": round(out["prediction"], 1),
            "high":       round(out["high"], 1),
        }
    except Exception as exc:
        result["m2"] = {"error": str(exc)}

    try:
        from api.predict_lgbm_harvest import schedule, load_artifacts as load_m3
        m3_art, m2_art = load_m3()
        out = schedule(df, m3_art, m2_art)
        today = out.get("today", {})
        result["m3"] = {
            "recommendation": out.get("recommendation", "—"),
            "harvest_pct":    today.get("harvest_pct", 0),
            "confidence":     today.get("confidence", 0),
            "tomorrow_pct":   out.get("tomorrow", {}).get("harvest_pct", 0),
        }
    except Exception as exc:
        result["m3"] = {"error": str(exc)}

    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})


@app.get("/sensors/{container_id}")
def get_sensors(container_id: str):
    """Return the latest sensor reading — live MQTT cache, or latest SQLite row as fallback."""
    from agent.sensors import get_sensor_reading
    from data.store import sensor_store

    data = get_sensor_reading(container_id)
    if not data:
        rows = sensor_store.get_latest(container_id, n=1)
        if rows:
            r = rows[0]
            data = {
                "pH":          r.get("pH"),
                "EC":          r.get("EC"),
                "DO":          r.get("DO"),
                "temperature": r.get("temperature"),
                "luminosity":  r.get("luminosity"),
                "turbidity":   r.get("turbidity"),
                "timestamp":   r.get("date"),
                "status":      "ok",
                "source":      "db",
            }

    return JSONResponse(content=data or {}, headers={"Cache-Control": "no-store"})


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
        "tier":         req.tier,
        "chat_history": history,
    })

    response   = result.get("response",   "Sorry, something went wrong.")
    content    = result.get("content",    {"type": "text", "text": response})
    tools_used = result.get("tools_used", [])
    intent     = result.get("intent",     "")
    confidence = result.get("confidence",  0.0)

    history.append({"role": "assistant", "content": response})
    memory_store.save(req.user_id, history)

    return ChatResponse(
        response=response,
        content=content,
        tools_used=tools_used,
        intent=intent,
        confidence=confidence,
    )


@app.get("/alerts/{user_id}")
async def alerts_sse(user_id: str, container_id: str = ""):
    """Server-Sent Events stream — pushes proactive alerts to the browser."""
    # Register session immediately so the monitor starts watching this container
    # even before the user sends a chat message.
    if container_id:
        from agent.monitor import register_session
        register_session(user_id, container_id)

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
