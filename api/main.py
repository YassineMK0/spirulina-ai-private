"""SpirulinaAI FastAPI backend.

Start:
    .venv\\Scripts\\uvicorn api.main:app --reload --port 8000

Endpoints
---------
    POST   /chat                                   -> invoke agent, return response
    GET    /conversations/{user_id}                -> list conversations
    POST   /conversations/{user_id}                -> create new conversation
    DELETE /conversations/{user_id}/{conv_id}      -> delete conversation
    GET    /conversations/{user_id}/{conv_id}      -> get messages for conversation
    PATCH  /conversations/{user_id}/{conv_id}/title-> rename conversation
    GET    /health                                 -> liveness check
    GET    /alerts/{user_id}                       -> SSE proactive alerts
    GET    /sensors/{container_id}                 -> latest sensor reading
    GET    /models/{container_id}                  -> ML model outputs
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()


# ---------------------------------------------------------------------------
# SSE alert queues
# ---------------------------------------------------------------------------

_alert_queues: dict[str, asyncio.Queue] = {}
_event_loop = None


def _push_alert(user_id: str, alert_text: str) -> None:
    q = _alert_queues.get(user_id)
    if q and _event_loop:
        _event_loop.call_soon_threadsafe(q.put_nowait, alert_text)
        print(f"[alert] pushed to user={user_id[:8]}...")
    else:
        print(f"[alert] DROPPED — queue={q is not None} loop={_event_loop is not None} user={user_id[:8]}...")


def _background_warmup():
    try:
        from rag.retriever.retrieve import _get_collection, _get_bm25_index
        _get_collection()
        _get_bm25_index(None, None)
        print("[warmup] bge-m3 + BM25 ready")
    except Exception as e:
        print(f"[warmup] retriever: {e}")
    for name, loader in [
        ("M1 IsolationForest", lambda: __import__("api.predict_isolationforest", fromlist=["load_artifact"]).load_artifact()),
        ("M2 LightGBM",       lambda: __import__("api.predict_lgbm",          fromlist=["load_artifact"]).load_artifact()),
        ("M3 harvest",        lambda: __import__("api.predict_lgbm_harvest",  fromlist=["load_artifacts"]).load_artifacts()),
    ]:
        try:
            loader()
            print(f"[warmup] {name} ready")
        except Exception as e:
            print(f"[warmup] {name}: {e}")
    print("[warmup] done")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    try:
        from agent.graph import graph as _g
        global _graph
        _graph = _g
        print("[startup] graph compiled")
    except Exception as e:
        print(f"[startup] graph failed: {e}")

    threading.Thread(target=_background_warmup, daemon=True, name="warmup").start()

    try:
        from agent.sensors import start_mqtt_subscriber
        start_mqtt_subscriber()
        print("[startup] MQTT subscriber started")
    except Exception as e:
        print(f"[startup] MQTT: {e}")

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from agent.monitor import run_monitor_check
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: run_monitor_check(_push_alert), "interval", seconds=15, max_instances=3)
        scheduler.start()
        print("[startup] monitor scheduler started")
    except Exception as e:
        print(f"[startup] scheduler: {e}")
        scheduler = None

    print("[startup] ready")
    yield

    try:
        if scheduler:
            scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(title="SpirulinaAI", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "DELETE", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

from api.auth  import router as auth_router
from api.admin import router as admin_router
app.include_router(auth_router)
app.include_router(admin_router)

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
    message:         str
    user_id:         str   = "anonymous"
    container_id:    str   = ""
    tier:            str   = "free"
    conversation_id: str   = ""      # empty = create new conversation automatically


class ChatResponse(BaseModel):
    response:        str
    content:         dict  = {}
    tools_used:      list  = []
    intent:          str   = ""
    confidence:      float = 0.0
    plan:            str   = ""
    tool_calls:      list  = []
    conversation_id: str   = ""      # always returned so frontend can track it


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class TitleUpdate(BaseModel):
    title: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    """Diagnostic endpoint — shows active monitor sessions and SSE connections."""
    from agent.monitor import get_active_sessions
    from agent.sensors import get_sensor_reading, _cache
    sessions = get_active_sessions()
    return {
        "active_sessions":    sessions,
        "sse_connected_users": list(_alert_queues.keys()),
        "event_loop_ready":   _event_loop is not None,
        "cached_containers":  list(_cache.keys()),
        "latest_sensors":     {cid: get_sensor_reading(cid) for cid in _cache},
    }


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

@app.get("/conversations/{user_id}")
def list_conversations(user_id: str):
    """Return all conversations for a user, newest first."""
    from data.conversations import conversation_store
    return conversation_store.list_conversations(user_id)


@app.post("/conversations/{user_id}", status_code=201)
def create_conversation(user_id: str, body: ConversationCreate):
    """Explicitly create a new conversation (title can be set later)."""
    from data.conversations import conversation_store
    cid = conversation_store.create_conversation(user_id, body.title)
    return {"id": cid, "title": body.title}


@app.get("/conversations/{user_id}/{conv_id}")
def get_conversation_messages(user_id: str, conv_id: str):
    """Return the message list for one conversation."""
    from data.conversations import conversation_store
    if not conversation_store.conversation_exists(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation_store.get_messages(conv_id)


@app.delete("/conversations/{user_id}/{conv_id}")
def delete_conversation(user_id: str, conv_id: str):
    from data.conversations import conversation_store
    conversation_store.delete_conversation(conv_id)
    return {"status": "deleted"}


@app.patch("/conversations/{user_id}/{conv_id}/title")
def rename_conversation(user_id: str, conv_id: str, body: TitleUpdate):
    from data.conversations import conversation_store
    conversation_store.update_title(conv_id, body.title)
    return {"status": "updated", "title": body.title}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

FREE_TIER_LIMIT = 3  # max messages for free-tier users


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    from data.conversations import conversation_store, make_title
    from data.users import user_store
    from agent.monitor import register_session

    register_session(req.user_id, req.container_id)

    # ── Resolve actual tier from DB (don't trust client-sent tier) ──────────
    db_user    = user_store.get_by_id(req.user_id)
    actual_tier = db_user["tier"] if db_user else req.tier

    # ── Enforce free-tier message quota ─────────────────────────────────────
    if actual_tier == "free":
        used = user_store.count_messages(req.user_id)
        if used >= FREE_TIER_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Free tier limit reached ({FREE_TIER_LIMIT} messages). "
                    "Upgrade to Pro for unlimited access."
                ),
            )

    # ── Resolve / create conversation ───────────────────────────────────────
    conv_id = req.conversation_id.strip()
    is_new  = False

    if not conv_id or not conversation_store.conversation_exists(conv_id):
        title   = make_title(req.message)
        conv_id = conversation_store.create_conversation(req.user_id, title)
        is_new  = True

    # ── Load history and append user message ────────────────────────────────
    history = conversation_store.get_messages(conv_id)
    conversation_store.add_message(conv_id, "user", req.message)
    history.append({"role": "user", "content": req.message})

    # ── Run LangGraph pipeline ───────────────────────────────────────────────
    result = _get_graph().invoke({
        "user_id":      req.user_id,
        "container_id": req.container_id,
        "tier":         actual_tier,
        "chat_history": history,
    })

    response   = result.get("response",   "Sorry, something went wrong.")
    content    = result.get("content",    {"type": "text", "text": response})
    tools_used = result.get("tools_used", [])
    intent     = result.get("intent",     "")
    confidence = float(result.get("confidence", 0.0))
    plan       = result.get("plan",       "")
    tool_calls = result.get("tool_calls", [])

    # ── Persist assistant reply ──────────────────────────────────────────────
    conversation_store.add_message(conv_id, "assistant", response)

    return ChatResponse(
        response=response,
        content=content,
        tools_used=tools_used,
        intent=intent,
        confidence=confidence,
        plan=plan,
        tool_calls=tool_calls,
        conversation_id=conv_id,
    )


# ---------------------------------------------------------------------------
# Sensors / ML
# ---------------------------------------------------------------------------

@app.get("/sensors/{container_id}")
def get_sensors(container_id: str):
    from agent.sensors import get_sensor_reading
    from data.store import sensor_store

    data = get_sensor_reading(container_id)
    if not data:
        rows = sensor_store.get_latest(container_id, n=1)
        if rows:
            r    = rows[0]
            data = {
                "pH": r.get("pH"), "EC": r.get("EC"), "DO": r.get("DO"),
                "temperature": r.get("temperature"), "luminosity": r.get("luminosity"),
                "turbidity": r.get("turbidity"), "timestamp": r.get("date"),
                "status": "ok", "source": "db",
            }
    return JSONResponse(content=data or {}, headers={"Cache-Control": "no-store"})


@app.get("/models/{container_id}")
def get_model_outputs(container_id: str):
    import numpy as np
    import pandas as pd
    from agent.sensors import get_history

    history = get_history(container_id)
    if not history:
        return JSONResponse(content={"error": "no_data"}, headers={"Cache-Control": "no-store"})

    df     = pd.DataFrame(history)
    result = {"m1": {}, "m2": {}, "m3": {}, "readings": len(history)}

    try:
        from api.predict_isolationforest import predict_df, load_artifact as load_m1
        out  = predict_df(df, load_m1())
        last = out.iloc[-1]
        score = float(last["anomaly_score"]) if not np.isnan(last["anomaly_score"]) else 0.0
        result["m1"] = {"anomaly": bool(last["is_anomaly"]), "score": round(score, 4),
                        "severity": str(last["severity"]), "trend": str(last["trend_direction"])}
    except Exception as exc:
        result["m1"] = {"error": str(exc)}

    try:
        from api.predict_lgbm import predict, load_artifact as load_m2
        out = predict(df, load_m2())
        result["m2"] = {"low": round(out["low"], 1), "prediction": round(out["prediction"], 1),
                        "high": round(out["high"], 1)}
    except Exception as exc:
        result["m2"] = {"error": str(exc)}

    try:
        from api.predict_lgbm_harvest import schedule, load_artifacts as load_m3
        m3_art, m2_art = load_m3()
        out   = schedule(df, m3_art, m2_art)
        today = out.get("today", {})
        result["m3"] = {"recommendation": out.get("recommendation", ""),
                        "harvest_pct": today.get("harvest_pct", 0),
                        "confidence":  today.get("confidence",  0),
                        "tomorrow_pct": out.get("tomorrow", {}).get("harvest_pct", 0)}
    except Exception as exc:
        result["m3"] = {"error": str(exc)}

    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# SSE alerts
# ---------------------------------------------------------------------------

@app.get("/alerts/{user_id}")
async def alerts_sse(user_id: str, container_id: str = ""):
    if container_id:
        from agent.monitor import register_session
        register_session(user_id, container_id)

    q: asyncio.Queue = asyncio.Queue()
    _alert_queues[user_id] = q

    async def event_stream():
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                try:
                    text    = await asyncio.wait_for(q.get(), timeout=30.0)
                    payload = json.dumps({"type": "alert", "text": text})
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _alert_queues.pop(user_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

