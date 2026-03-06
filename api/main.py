"""SpirulinaAI FastAPI backend.

Start:
    .venv\\Scripts\\uvicorn api.main:app --reload --port 8000

Endpoints:
    POST /chat   -> invoke LangGraph pipeline, return AI response
    GET  /health -> liveness check
"""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="SpirulinaAI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lazy-load the graph so the embedding model warms up on first request,
# not at import time (keeps uvicorn startup fast).
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

class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo-user"
    container_id: str = ""
    chat_history: list[Message] = []


class ChatResponse(BaseModel):
    response: str
    intent: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    history = [m.model_dump() for m in req.chat_history]
    history.append({"role": "user", "content": req.message})

    state: dict[str, Any] = {
        "user_id":      req.user_id,
        "container_id": req.container_id,
        "chat_history": history,
    }

    result = _get_graph().invoke(state)

    return ChatResponse(
        response   = result.get("response", "Sorry, something went wrong."),
        intent     = result.get("intent",   ""),
        confidence = result.get("confidence", 0.0),
    )
