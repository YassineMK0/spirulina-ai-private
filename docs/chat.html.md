# chat.html

## Purpose
The sole frontend for SpirulinaAI. A self-contained single-page HTML/JS chat interface that communicates with the FastAPI backend.

## How it works
- Sends user messages to `POST /chat` via `fetch()`
- Displays streamed or JSON responses in a chat bubble UI
- Maintains conversation history in the browser session
- No build step — open directly in a browser or serve via FastAPI static files

## Key features
- Multi-turn conversation display
- Markdown rendering for formatted LLM responses
- Loading indicator while waiting for responses
- Container ID input (used to link a user to a specific spirulina container)

## Usage
Start the API server, then open `chat.html` in a browser:
```bash
.venv\Scripts\uvicorn api.main:app --reload --port 8000
# Open http://127.0.0.1:8000 or open chat.html directly
```

## Test containers
Use any of these as container ID to test the reasoning agent:
- `test-harvest-ready` — triggers harvest decision
- `test-ph-crash` — triggers anomaly diagnosis
- `test-multi-anomaly` — triggers multi-issue analysis
