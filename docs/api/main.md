# api/main.py

## Purpose
The FastAPI backend server. Exposes HTTP endpoints that the frontend (chat.html or any client) calls to interact with the SpirulinaAI pipeline.

## How to start
```bash
.venv\Scripts\uvicorn api.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Send a message, get an AI response |
| `GET` | `/history/{user_id}` | Return stored chat history for a user |
| `DELETE` | `/history/{user_id}` | Clear chat history for a user |
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |

## `/chat` endpoint (main flow)
1. Loads user's history from Redis/InMemory via `memory_store.get(user_id)`
2. Appends the new user message to history
3. Invokes the LangGraph pipeline with `{user_id, container_id, chat_history}`
4. Saves updated history back to memory store (auto-capped at 10 turns)
5. Returns `{response, intent, confidence}`

## Request/Response schemas
```
ChatRequest:
  message:      str          (required)
  user_id:      str = "anonymous"
  container_id: str = ""

ChatResponse:
  response:     str
  intent:       str
  confidence:   float
```

## Startup pre-warming (`lifespan`)
On uvicorn start, before the first request:
1. Compiles the LangGraph graph (loads model weights)
2. Pre-loads ChromaDB collection + BM25 index
This ensures the first user message responds quickly instead of waiting for cold-start loading.

## CORS
All origins, methods, and headers are allowed (`allow_origins=["*"]`). Tighten this for production.

## Graph singleton
`_graph` is a module-level variable set at startup. `_get_graph()` lazily compiles it if not already done.

## Dependencies
- `fastapi`, `uvicorn`, `pydantic`
- `agent.graph` — compiled LangGraph graph
- `agent.memory` — `memory_store`
- `python-dotenv` — loads `.env` at startup
