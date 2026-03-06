# Spirulina -- Project Progress

## What we built so far

A **LangGraph-based agent pipeline** for a spirulina smart-farming assistant.
The system takes a user message, figures out what they want (intent), and routes
it through the right processing stages (knowledge lookup, ML models, sensors)
before generating a response.

---

## Tasks completed

### Task 1 -- Project scaffolding
Set up the full folder structure, virtual environment, and dependencies.

- Created `/agent`, `/rag`, `/ml`, `/api`, `/data`, `/notebooks`, `/tests`
- Wrote `requirements.txt` with LangGraph, LangChain, FastAPI, ChromaDB, scikit-learn, etc.
- Wrote `.env.template` with all config variables
- Wrote `README.md` explaining each folder
- Installed everything into `.venv`

### Task 2 -- Agent state schema + graph skeleton
Defined the shared state that flows through every node and wired up
placeholder nodes in a linear pipeline.

- Created `AgentState` TypedDict with 10 fields
- Built 6 placeholder nodes (check_container, classify_intent, retrieve_rag,
  run_ml_models, read_sensors, generate_response)
- Compiled the LangGraph `StateGraph` and verified state passes through all nodes

### Task 3 -- Intent Router (LLM-backed)
Replaced the placeholder `classify_intent` with a real LLM-powered intent
classifier. Added a SYSTEM intent, JSON output with confidence scores, and
a clarification fallback when the model isn't sure.

- Rewired the graph with two conditional gates (container gate + confidence gate)
- Added `request_clarification` node for low-confidence cases
- Wrote and ran a 30-message test suite -- **90% accuracy** on first run

---

## File-by-file breakdown

### `agent/state.py`
The **shared state schema** (`AgentState` TypedDict). Every node in the graph
reads from and writes to this single dict. Fields:

| Field              | Type          | Purpose                                   |
|--------------------|---------------|-------------------------------------------|
| `user_id`          | str           | Who is talking                            |
| `container_id`     | str           | Which grow-container is linked            |
| `has_container`    | bool          | Whether a container was found             |
| `intent`           | str           | Classified intent (KNOWLEDGE/UPDATE/etc.) |
| `confidence`       | float         | How sure the router is (0.0-1.0)         |
| `rag_context`      | str           | Retrieved knowledge chunks                |
| `ml_outputs`       | dict          | ML model predictions                     |
| `chat_history`     | list[dict]    | Conversation messages (append-only)       |
| `last_sensor_state`| dict          | Latest sensor telemetry                   |
| `response`         | str           | Final answer to the user                  |

### `agent/intent_router.py`
The **intent classification node**. This is the brain of the routing system.

- **Prompt**: asks the LLM to return JSON `{"intent": "...", "confidence": 0.95}`
- **4 intents**: KNOWLEDGE, UPDATE, HARVEST, SYSTEM (+ UNKNOWN fallback)
- **LLM providers**: Groq (default, `llama-3.1-8b-instant`), OpenAI (`gpt-4o-mini`), or Ollama (local Mistral-7B)
- **Chain**: `ChatPromptTemplate | ChatGroq | StrOutputParser`
- **Parser**: `_parse_response()` handles markdown fences, trailing text, malformed JSON gracefully
- **Confidence threshold**: 0.7 -- below this, the graph routes to clarification

### `agent/nodes.py`
**Placeholder node functions** for every pipeline stage except intent classification.
Each node receives the full state dict and returns a partial update. Currently
these are stubs that pass through existing state -- they'll be filled in as we
build out RAG, ML, and sensor integrations.

Nodes defined:
- `check_container` -- resolves `container_id` and sets `has_container`
- `retrieve_rag` -- (placeholder) vector-store lookup
- `run_ml_models` -- (placeholder) ML inference
- `read_sensors` -- (placeholder) sensor telemetry
- `request_clarification` -- asks user to rephrase when confidence < 0.7
- `generate_response` -- (placeholder) composes final answer

### `agent/graph.py`
The **LangGraph StateGraph wiring** -- connects all nodes with edges and
conditional routing. This is the central orchestration file.

Pipeline flow:
```
check_container
    |
    +-- has_container=False --> generate_response --> END
    |
    +-- has_container=True  --> classify_intent
                                    |
                                    +-- confidence >= 0.7 --> retrieve_rag
                                    |                           --> run_ml_models
                                    |                           --> read_sensors
                                    |                           --> generate_response
                                    |                           --> END
                                    |
                                    +-- confidence < 0.7  --> request_clarification
                                                              --> END
```

Also contains a `__main__` smoke test that verifies both paths (no container
and with container + live LLM).

### `tests/test_intent_router.py`
**30-message test suite** covering all 4 intents (~8 messages each).
Calls `classify_intent()` directly and compares against expected labels.

Results from last run:
- 27/30 correct (90% accuracy)
- 0 low-confidence triggers
- 3 edge cases misclassified (genuinely ambiguous messages)

Run with: `.venv\Scripts\python -m tests.test_intent_router`

### `requirements.txt`
All Python dependencies: LangGraph, LangChain, FastAPI, ChromaDB,
scikit-learn, pandas, numpy, Jupyter, etc.

### `.env.template`
Config template. Copy to `.env` and fill in your API keys.
Currently configured for **Groq** with `llama-3.1-8b-instant`.

### `README.md`
Quick-start guide and folder structure overview.

---

## Current stack

| Component       | Technology                     |
|----------------|-------------------------------|
| Agent framework | LangGraph + LangChain         |
| LLM provider    | Groq (free tier)              |
| LLM model       | llama-3.1-8b-instant          |
| API (planned)   | FastAPI + uvicorn             |
| Vector store    | ChromaDB (planned)            |
| ML              | scikit-learn (planned)        |
| Environment     | Python 3.10, Windows          |

---

## What's next

- [ ] Build the RAG pipeline (embedder, retriever, generator)
- [ ] Wire up real sensor reading logic
- [ ] Add ML model nodes (growth prediction, anomaly detection)
- [ ] Build the FastAPI endpoint
- [ ] Add intent-based routing (KNOWLEDGE->RAG, UPDATE->write, HARVEST->ML, SYSTEM->sensors)
