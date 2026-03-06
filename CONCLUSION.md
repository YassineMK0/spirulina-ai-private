# SpirulinaAI — Project Conclusion (Phase 1)

## What Was Built

This document summarises the first phase of the SpirulinaAI project:
an AI-powered assistant for Spirulina platensis farm operators, built on
LangGraph + LangChain + Groq + ChromaDB.

---

## Architecture Overview

```
User Message
     │
     ▼
┌─────────────────┐
│ check_container │  Resolves container_id → has_container flag
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ classify_intent │  Groq llama-3.1-8b-instant
│  (Intent Router)│  Returns {intent, confidence}
└────────┬────────┘
         │
    [confidence gate]
    ≥ 0.7 │           < 0.7
          │               │
          ▼               ▼
   ┌─────────────┐  ┌─────────────────────┐
   │ retrieve_rag│  │ request_clarification│ ──► END
   │  (ChromaDB) │  └─────────────────────┘
   └──────┬──────┘
          │
     [ml gate]
  has_container=True │     has_container=False
                     │              │
                     ▼              │
           ┌──────────────────┐     │
           │  run_ml_models   │     │
           └────────┬─────────┘     │
                    │               │
                    ▼               │
           ┌──────────────────┐     │
           │   read_sensors   │     │
           └────────┬─────────┘     │
                    │               │
                    └───────┬───────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ generate_response│  Groq llama-3.3-70b-versatile
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ format_response  │  Markdown templates
                  └────────┬─────────┘
                           │
                          END
```

---

## Components Built

### 1. Project Scaffold
- Clean folder structure: `agent/`, `rag/`, `ml/`, `api/`, `data/`, `tests/`, `notebooks/`
- `requirements.txt`, `.env.template`, `README.md` at root
- Python virtual environment at `.venv/`

---

### 2. Agent State (`agent/state.py`)
Shared TypedDict schema passed through every node.

| Field | Type | Set by |
|---|---|---|
| `user_id` | str | caller |
| `container_id` | str | caller |
| `has_container` | bool | check_container |
| `intent` | str | classify_intent |
| `confidence` | float | classify_intent |
| `rag_context` | str | retrieve_rag |
| `ml_outputs` | dict | run_ml_models |
| `chat_history` | list (append-only) | format_response |
| `last_sensor_state` | dict | read_sensors |
| `response` | str | generate_response / format_response |

---

### 3. Intent Router (`agent/intent_router.py`)
- **Model**: Groq `llama-3.1-8b-instant` (fast, free)
- **Output**: `{"intent": "KNOWLEDGE", "confidence": 0.95}`
- **Intents**: `KNOWLEDGE` / `UPDATE` / `HARVEST` / `SYSTEM`
- **Confidence gate**: routes to clarification node when confidence < 0.7
- **Result**: 27/30 correct on 30-message eval suite — **90% accuracy**

---

### 4. RAG Pipeline

#### Ingestion (`rag/embedder/ingest.py`)
- **PDF**: PyMuPDF — blocks-based extraction, strips top/bottom 8% of page (headers/footers)
- **DOCX**: python-docx paragraph extraction
- **JSON**: Q&A pair parser (`question/answer` or `q/a` keys)
- **MD/TXT**: plain read with whitespace normalisation
- **Chunking**: `RecursiveCharacterTextSplitter(chunk_size=500, overlap=50)`
- **Metadata per chunk**: `{source, doc_type, topic, page, chunk}`
- **Topic auto-detection** from subfolder name:

| Folder | Topic tag |
|---|---|
| `data/raw/papers/` | `scientific_literature` |
| `data/raw/manuals/` | `cultivation_manual` |
| `data/raw/qa/` | `qa_pairs` |
| `data/raw/troubleshooting/` | `troubleshooting` |

- **Storage**: ChromaDB persistent collection `spirulina_kb` at `data/processed/chroma/`
- **Target**: 500–1000 chunks after full KB ingestion
- **Status**: 9 PDF source files placed in `data/raw/`

#### Embedding Model
**`paraphrase-multilingual-MiniLM-L12-v2`** (sentence-transformers)
- Free, local, no API key
- 50+ language support (English + French docs)
- 384-dimensional embeddings

#### Retriever (`rag/retriever/retrieve.py`)
- Top-k vector similarity query (default top-5)
- Optional metadata filters: `topic` and `doc_type`
- Returns: `{text, source, doc_type, topic, page, score}`

#### Retrieval Tuning Infrastructure
- **`tests/eval_set.py`**: 20 hand-written query/keyword pairs, 5 per topic
- **`tests/tune_retrieval.py`**: 18-config grid search
  - chunk_size `[300, 500, 800]` × top_k `[3, 5, 8]` × filter `[on, off]`
  - Declares winner at ≥ 80% hit rate

---

### 5. RAG Generator (`rag/generator/generate.py`)
- **Model**: Groq `llama-3.3-70b-versatile` (stronger synthesis than 8B)
- **Persona**: SpirulinaAI — senior cultivation expert, chat-first, no-dashboard philosophy

**8 behaviour rules enforced by the system prompt:**

| Rule | Behaviour |
|---|---|
| 1 — Grounded | Answers trace back to retrieved context only |
| 2 — Admit uncertainty | Opens with "My knowledge base doesn't cover that" |
| 3 — Sensor check first | Names which parameter to measure before advising |
| 4 — No dose guessing | Never gives quantities without sensor readings |
| 5 — Partial coverage | Answers what it can, flags the gap explicitly |
| 6 — Cite sources | References document names when visible in context |
| 7 — Escalate crises | Culture crash / severe contamination → specialist |
| 8 — One question at a time | Asks for exactly one missing reading |

**4 few-shot tone examples** embedded in the prompt for consistent voice.

---

### 6. Response Formatter (`agent/formatter.py`)
Five markdown templates auto-selected and combined by intent:

| Template | Trigger | Output |
|---|---|---|
| RAG answer | always | LLM text + `📚 Sources: file1 · file2` |
| Sensor card | `UPDATE` / `SYSTEM` + sensor data | `📊` table with ✅ ⚠️ 🔴 per row |
| Prediction | ML has `growth_prediction` | `🔮 60-Minute Forecast` table |
| Harvest window | `HARVEST` + ML data | `🌾` three-scenario card + OD680 |
| Alert banner | Out-of-range sensors / `SYSTEM` | ℹ️ / ⚠️ / 🚨 with action line |

**Sensor thresholds built in:**

| Sensor | ✅ Normal | ⚠️ Warning | 🔴 Critical |
|---|---|---|---|
| pH | 8.5–10.5 | 8.0–11.0 | outside |
| EC | 20–35 mS/cm | 15–45 | outside |
| Temperature | 30–38 °C | 25–42 | outside |
| OD680 | 0.4–1.2 | 0.2–1.5 | outside |
| Light | 5 000–40 000 lux | 2 000–60 000 | outside |

---

### 7. Test Suite (`tests/`)

| File | Type | Status |
|---|---|---|
| `test_intent_router.py` | 30-msg accuracy eval (Groq) | 90% — 27/30 |
| `test_routing_gate.py` | 5 unit tests, no API needed | 5/5 passing |
| `eval_set.py` | 20 query/keyword pairs | Ready |
| `tune_retrieval.py` | 18-config grid search | Ready (needs KB files ingested) |
| `test_retrieval.py` | 10-query live retrieval test | Ready (needs KB files ingested) |
| `test_system_prompt.py` | 20-question prompt quality test | Ready (needs GROQ_API_KEY) |

---

## Model Split

| Role | Model | Provider | Reason |
|---|---|---|---|
| Intent router | `llama-3.1-8b-instant` | Groq | Fast, 4-label classification |
| RAG generator | `llama-3.3-70b-versatile` | Groq | Better context synthesis |
| Embedder | `paraphrase-multilingual-MiniLM-L12-v2` | Local | Free, multilingual |

Both LLM roles use the same Groq API key — one provider, zero cost.

---

## What Remains (Phase 2)

| Component | Status | Blocker |
|---|---|---|
| **RAG ingestion run** | Ready to execute | Drop files in subfolders, run `python -m rag.embedder.ingest` |
| **Retrieval tuning** | Ready to execute | Needs ingested ChromaDB |
| **Auth & Identity node** | Parked | DB technology not yet chosen (SQLite / PostgreSQL) |
| **ML models** | Planned | `ml/growth_prediction/`, `ml/anomaly_detection/`, `ml/harvest_readiness/` |
| **Sensor integration** | Placeholder | Real IoT reads in `read_sensors` node |
| **FastAPI layer** | Planned | `api/main.py` — expose graph as HTTP endpoint |

---

## Key Design Decisions

- **LangGraph** over a simple chain: enables conditional routing, parallel nodes, and stateful multi-turn conversations without managing state manually.
- **Groq free tier**: keeps the entire LLM layer at zero cost during development without sacrificing speed.
- **Local embeddings**: no API dependency at query time — retrieval works offline.
- **Two-gate routing**: confidence gate keeps bad classifications out of the pipeline; ML gate prevents container-specific nodes from running for general users.
- **Formatter as a separate node**: separates LLM generation from presentation — swapping templates or adding a new card never touches the generator.
- **Chat-first prompt philosophy**: the operator can already see their dashboard. SpirulinaAI adds value through interpretation, not readback.
