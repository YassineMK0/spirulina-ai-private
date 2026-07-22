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
    GET    /alerts/{user_id}/history               -> persisted alert history (classified)
    GET    /sensors/{container_id}                 -> latest sensor reading
    GET    /models/{container_id}                  -> ML model outputs
    POST   /cpc/predict                            -> CPC concentration from image (multipart)
    POST   /species/predict                        -> microalgae species classification from image (multipart)
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

from api.logging_setup import setup_logging
setup_logging()

import logging
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE alert queues
# ---------------------------------------------------------------------------

_alert_queues: dict[str, asyncio.Queue] = {}
_event_loop = None


# agent/monitor.py severity vocabulary -> frontend display vocabulary
_SEVERITY_DISPLAY = {"critical": "critical", "warning": "medium", "harvest": "low"}


def _push_alert(
    user_id: str,
    alert_text: str,
    severity: str = "warning",
    affected: list | None = None,
    source: str = "model",
    created_at: str | None = None,
) -> None:
    q = _alert_queues.get(user_id)
    if q and _event_loop:
        item = {
            "text":       alert_text,
            "severity":   _SEVERITY_DISPLAY.get(severity, "medium"),
            "affected":   affected or [],
            "source":     source,
            "created_at": created_at,
        }
        _event_loop.call_soon_threadsafe(q.put_nowait, item)
        log.info("alert pushed  user=%s", user_id[:8])
    else:
        log.warning("alert DROPPED  queue=%s loop=%s user=%s",
                    q is not None, _event_loop is not None, user_id[:8])


def _background_warmup():
    _wlog = logging.getLogger("spirulina.warmup")
    try:
        from rag.retriever.retrieve import _get_collection, _get_bm25_index
        _get_collection()
        _get_bm25_index(None, None)
        _wlog.info("bge-m3 + BM25 ready")
    except Exception as e:
        _wlog.error("retriever warmup failed: %s", e)
    try:
        from models.anomaly_model.detector import AnomalyDetector
        AnomalyDetector.load()
        _wlog.info("M1 anomaly detector ready")
    except Exception as e:
        _wlog.error("M1 anomaly detector warmup failed: %s", e)
    try:
        from models.cpc_model.predictor import CPCPredictor
        CPCPredictor.load()
        _wlog.info("CPC image predictor ready")
    except Exception as e:
        _wlog.error("CPC predictor warmup failed: %s", e)
    try:
        from models.species_classifier.predictor import SpeciesClassifier
        SpeciesClassifier.load()
        _wlog.info("species classifier ready")
    except Exception as e:
        _wlog.error("species classifier warmup failed: %s", e)
    _wlog.info("done")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    try:
        from agent.graph import graph as _g
        global _graph
        _graph = _g
        log.info("graph compiled")
    except Exception as e:
        log.error("graph failed: %s", e)

    threading.Thread(target=_background_warmup, daemon=True, name="warmup").start()

    try:
        from agent.sensors import start_mqtt_subscriber
        start_mqtt_subscriber()
        log.info("MQTT subscriber started")
    except Exception as e:
        log.error("MQTT startup failed: %s", e)

    try:
        import os

        from apscheduler.schedulers.background import BackgroundScheduler
        from agent.monitor import run_monitor_check, run_combination_model_check

        # Rule engine (check_thresholds + anomaly_model rules/seasonal): cheap,
        # runs on real MQTT cadence (default 900s = 15min). Override to e.g. 15s
        # locally for the agent/sensors.py crash simulator / fast demoing.
        rule_interval_seconds = int(os.getenv("MONITOR_RULE_INTERVAL_SECONDS", "900"))

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            lambda: run_monitor_check(_push_alert),
            "interval", seconds=rule_interval_seconds, max_instances=3,
        )
        # Combination model (LOF): slow-moving 24h-history signal, scored once
        # a day at a fixed wall-clock time rather than relative to app startup.
        scheduler.add_job(
            lambda: run_combination_model_check(_push_alert),
            "cron", hour=0, minute=5, max_instances=1,
        )
        scheduler.start()
        log.info("monitor scheduler started  rule_interval=%ss  combination_model=cron(00:05)",
                  rule_interval_seconds)
    except Exception as e:
        log.error("scheduler failed: %s", e)
        scheduler = None

    log.info("startup complete")
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


@app.get("/containers")
def list_containers():
    """List known container IDs — live MQTT cache + DB history, deduplicated."""
    from agent.sensors import _cache
    from data.store import sensor_store

    ids = set(_cache.keys()) | set(sensor_store.list_containers())
    return {"containers": sorted(ids) or ["container-01"]}


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


@app.post("/debug/run-combination-check/{container_id}")
def debug_run_combination_check(container_id: str):
    """Manually trigger the combination-model (LOF) check for one container,
    instead of waiting for its 00:05 daily cron tick. Dev/testing only --
    pairs with `python agent/sensors.py --backfill-24h` to seed enough
    history, then this fires the scoring immediately."""
    from agent.monitor import register_session, run_combination_model_check, _build_daily_context

    register_session(f"debug-{container_id}", container_id)
    daily_context = _build_daily_context(container_id)
    run_combination_model_check(_push_alert)
    return {
        "ran": True,
        "daily_context": daily_context,
        "note": "check the /alerts SSE stream or backend logs for the result; "
                "no daily_context means not enough history yet.",
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

    # get_sensor_reading() already falls back to the DB when the MQTT cache
    # is empty -- same function the chat agent's read_sensors node uses, so
    # the Dashboard and the chat agent never see different data.
    data = get_sensor_reading(container_id)
    return JSONResponse(content=data or {}, headers={"Cache-Control": "no-store"})


@app.get("/models/{container_id}")
def get_model_outputs(container_id: str):
    """M1 anomaly detector output -- the only ML model in the pipeline
    (rule engine + seasonal check). The combination model (LOF) layer isn't
    included here -- it's a 24h-cadence signal scored by its own cron job
    (agent.monitor.run_combination_model_check), not a per-request prediction."""
    from agent.monitor import _run_ml_prediction

    ml = _run_ml_prediction(container_id)
    if not ml:
        return JSONResponse(content={"error": "no_data"}, headers={"Cache-Control": "no-store"})

    return JSONResponse(content={"m1": ml}, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# CPC image prediction
# ---------------------------------------------------------------------------

@app.post("/cpc/predict")
async def cpc_predict(file: UploadFile = File(...)):
    """Predict CPC concentration (mg/mL) from a spirulina image.

    Accepts any common image format (JPEG, PNG, BMP …).
    Returns: cpc_mgml, unit, in_training_range, training_range.
    """
    from models.cpc_model.predictor import CPCPredictor

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(content=result)


@app.post("/species/predict")
async def species_predict(file: UploadFile = File(...)):
    """Classify a microalgae image as Chlamydomonas_Reinhardtii,
    Chlorella_FSP, or Spirulina_Platensis -- a non-Spirulina_Platensis
    result is a contamination signal.

    Accepts any common image format (JPEG, PNG, BMP …).
    Returns: species, confidence, probabilities, is_target_species, warning.
    """
    from models.species_classifier.predictor import SpeciesClassifier

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        predictor = SpeciesClassifier.load()
        result = predictor.predict_bytes(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# SSE alerts
# ---------------------------------------------------------------------------

@app.get("/alerts/{user_id}/history")
def alert_history(user_id: str, limit: int = 50):
    """Persisted alert history for a user, newest first -- classified by
    severity/source/affected sensors (see data/alerts.py). Used to hydrate
    the Alerts page on load so a refresh doesn't lose everything that only
    arrived over the live SSE stream previously."""
    from data.alerts import alert_store
    rows = alert_store.get_recent_for_user(user_id, limit)
    # DB rows store monitor.py's severity vocabulary (critical/warning/harvest);
    # translate to the frontend vocabulary so history rows match live SSE ones.
    for r in rows:
        r["severity"] = _SEVERITY_DISPLAY.get(r.get("severity"), "medium")
    return rows


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
                    item    = await asyncio.wait_for(q.get(), timeout=30.0)
                    payload = json.dumps({"type": "alert", **item})
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

