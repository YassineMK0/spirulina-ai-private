# SpirulinaAI

An intelligent assistant for spirulina cultivation. Answers questions, diagnoses problems, recommends harvest timing, and proactively alerts the container owner when sensor thresholds are breached — all powered by a dual-LLM agent pipeline.

---

## What it does

- **Answers cultivation questions** — pH, temperature, nutrients, light, EC, harvest timing (FR + EN)
- **Diagnoses problems** — yellow color, pH crash, contamination, slow growth, heat stress
- **Recommends harvest** — based on OD680 density readings and culture state
- **Proactive alerts** — monitors container sensors every 5 minutes, pushes real-time alerts to the chat UI without the user asking
- **Memory** — remembers conversation history across turns (Redis or in-memory fallback)

---

## Architecture

```
User message (chat.html)
        |
   POST /chat  (FastAPI)
        |
   LangGraph Pipeline
        |
   check_container
        |
   classify_intent  <-- Groq Llama 3.1 8B (fast router)
        |
   _route_after_classify
     |-- low confidence  --> request_clarification --> END
     |-- OFF_DOMAIN      --> reject_off_domain      --> END
     |-- MEMORY_RECALL   --> recall_memory           --> END
     +-- else            --> retrieve_rag
                                 |
                          _post_rag_gate
                     |---------------------|
              has_container             no container
                     |                     |
              run_ml_models         reasoning_agent or
                     |              generate_response
              read_sensors
                     |
           _post_sensors_gate
        |---------------------|
   HARVEST/SYSTEM        KNOWLEDGE/UPDATE
        |                     |
  reasoning_agent       generate_response
  (OpenRouter            (Groq Llama 3.3 70B
   Nemotron 120B)         fluent prose)
        |                     |
   format_response --> END
```

**Proactive monitoring (parallel background loop):**
```
APScheduler (every 5 min)
        |
   read sensors --> check thresholds --> breach?
                                            |
                                     generate alert (Nemotron 120B)
                                            |
                                     SSE push --> chat.html
```

---

## Intent labels

| Intent | Trigger | Generator |
|---|---|---|
| KNOWLEDGE | General cultivation questions | Llama 3.3 70B |
| UPDATE | Change a parameter / setting | Llama 3.3 70B |
| HARVEST | Harvest timing / readiness | Nemotron 120B |
| SYSTEM | Anomaly diagnosis, full system check | Nemotron 120B |
| OFF_DOMAIN | Unrelated questions | Redirect (no LLM) |
| MEMORY_RECALL | "What did we discuss?" | History lookup (no LLM) |
| UNKNOWN (< 0.7 confidence) | Ambiguous input | Clarification question |

---

## LLM Stack

| Role | Provider | Model |
|---|---|---|
| Intent router | Groq | llama-3.1-8b-instant |
| RAG generator | Groq | llama-3.3-70b-versatile |
| Reasoning agent | OpenRouter | nvidia/nemotron-3-super-120b-a12b:free |
| Query summarizer | Groq | llama-3.1-8b-instant |

---

## RAG Pipeline

- **Vector store:** ChromaDB at `data/processed/chroma/`
- **Embedding model:** `BAAI/bge-m3` (multilingual, 1024 dims) — runs locally
- **Retrieval:** Hybrid BM25 + dense search merged with RRF (Reciprocal Rank Fusion)
- **Corpus:** 5000+ chunks from 20+ documents (French + English)
- **Top-K:** 8 chunks per query

---

## Project structure

```
agent/
  graph.py          LangGraph pipeline — nodes + routing gates
  nodes.py          All node functions (RAG, sensors, clarification, etc.)
  intent_router.py  LLM-based intent classification
  sensors.py        Sensor reading interface (mock + named test containers)
  monitor.py        Threshold rules + alert generation
  memory.py         Redis / in-memory conversation history
  formatter.py      Response formatting (markdown, sensor table)
  state.py          AgentState TypedDict schema
  auth.py           User/container ID resolution

api/
  main.py           FastAPI app — /chat, /alerts (SSE), /history, /health

rag/
  embedder/ingest.py      Ingest documents into ChromaDB
  retriever/retrieve.py   Hybrid BM25+dense retrieval
  generator/generate.py   Dual-LLM generation (RAG + reasoning)

tests/
  test_conversations.py   50 end-to-end conversation scenarios (90.7% score)
  test_edge_cases.py      5 edge case tests (ambiguous, off-domain, etc.)
  test_intent_router.py   30 intent classification tests (90% accuracy)
  test_retrieval.py       Retrieval quality tests

docs/                     Code explanation files for every module
data/
  raw/                    Source documents (PDFs, markdown guides)
  processed/chroma/       ChromaDB vector store

chat.html                 Single-page chat UI (no build step)
requirements.txt
.env.template
```

---

## Quick start

```bash
# 1. Create virtualenv
python -m venv .venv313 && .venv313\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.template .env
# Edit .env — add GROQ_API_KEY and OPENROUTER_API_KEY

# 4. Ingest documents into ChromaDB (first time only)
python -m rag.embedder.ingest

# 5. Start the server
.venv313\Scripts\uvicorn api.main:app --port 8000

# 6. Open chat.html in your browser
```

---

## Environment variables

```env
GROQ_API_KEY=...                          # Groq free tier
OPENROUTER_API_KEY=...                    # OpenRouter (Nemotron 120B)
DEEPSEEK_API_KEY=...                      # Optional: DeepSeek R1 reasoning

INTENT_MODEL_NAME=llama-3.1-8b-instant
GENERATOR_MODEL_PROVIDER=groq
GENERATOR_MODEL_NAME=llama-3.3-70b-versatile
REASONING_MODEL_NAME=nvidia/nemotron-3-super-120b-a12b:free

EMBED_MODEL=BAAI/bge-m3
CHROMA_PERSIST_DIR=./data/processed/chroma
REDIS_URL=redis://localhost:6379          # Optional — falls back to in-memory
```

---

## Test containers (for development)

Use these as container ID in the chat UI to test the reasoning agent and alerts:

| Container ID | Scenario |
|---|---|
| `test-healthy` | All values optimal — no alert |
| `test-harvest-ready` | OD680 at 1.15 — harvest alert |
| `test-ph-crash` | pH 7.2 — critical pH alert |
| `test-heat-stress` | Temp 41.5 C — overheating alert |
| `test-high-ec` | EC 38 mS/cm — salinity alert |
| `test-multi-anomaly` | pH + heat + low O2 — multiple alerts |
| `test-rotating` | Cycles through all states every 5 min — for alert testing |

---

## Running tests

```bash
# 50 conversation scenarios
.venv313\Scripts\python -m tests.test_conversations

# Edge case tests (no API key needed — fully mocked)
.venv313\Scripts\python -m tests.test_edge_cases

# Intent router accuracy
.venv313\Scripts\python -m tests.test_intent_router
```

---

## RAG Evaluation (RAGAS metrics)

Evaluated on 30 questions across 3 categories using `llama-3.3-70b-versatile` as judge.
Retrieval: top-k=8, hybrid BM25+dense RRF.

| Category | Relevance | Faithfulness | Recall |
|---|---|---|---|
| Factual (10 Q) | 0.730 | 0.930 | 0.700 |
| Troubleshooting (10 Q) | 1.000 | 0.990 | 0.867 |
| Operational (10 Q) | 0.900 | 0.883 | 0.733 |
| **Overall** | **0.873** | **0.942** | **0.767** |

Thresholds: relevance > 0.80, faithfulness > 0.85, recall > 0.70 — **all pass**.

Results saved to `data/processed/rag_eval_results.json`.

---

## Key design decisions

- **Dual-LLM:** fluent prose generator (Llama 70B) for knowledge questions, step-by-step reasoning agent (Nemotron 120B) for harvest and anomaly analysis
- **Hybrid retrieval:** BM25 + dense vectors merged with RRF — better recall than dense-only, especially for technical French terms
- **Proactive monitoring:** APScheduler runs independently of user messages, pushes SSE alerts — container owner gets alerted even when not actively chatting
- **Dedup by breach label:** alerts deduplicate on the anomaly type, not the LLM text — avoids both spam and missed alerts when conditions change
