# api/ — FastAPI Layer

Exposes the LangGraph pipeline as an HTTP API.

**Status: planned — not yet implemented.**

---

## Planned Endpoints

### `POST /chat`
Main conversation endpoint. Invokes the full LangGraph pipeline and
returns the assistant's response.

```json
Request:
{
  "user_id":      "user-123",
  "container_id": "CTR-001",    // omit if no container linked
  "message":      "What pH should I target today?",
  "session_id":   "abc-xyz"     // for history continuity
}

Response:
{
  "response": "Based on your current readings...",
  "intent":   "KNOWLEDGE",
  "sources":  ["paper1.pdf", "manuel_zarrouk.pdf"]
}
```

### `POST /ingest`
Triggers a re-ingestion of `data/raw/` (admin only).

### `GET /health`
Returns service status and ChromaDB chunk count.

---

## Planned File Structure

```
api/
    main.py          # FastAPI app, route definitions
    schemas.py       # Pydantic request/response models
    session.py       # In-memory / Redis session store for chat history
    auth.py          # JWT decode middleware (future)
```

---

## Config

```
API_HOST=0.0.0.0
API_PORT=8000
```

Run (once implemented):
```bash
.venv/Scripts/python -m uvicorn api.main:app --reload
```
