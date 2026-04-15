# SpirulinaAI — Project Report

**Project:** AI-Powered Assistant for Spirulina Cultivation  
**Phase:** A — RAG Agent (complete)  
**Date:** April 2026

---

## 1. Context and Objective

Spirulina (*Spirulina platensis*) cultivation requires continuous monitoring of
biological and chemical parameters: pH, temperature, optical density, electrical
conductivity, dissolved oxygen, and light exposure. Farmers — particularly small
and medium producers — often lack access to expert guidance when anomalies occur
or when decisions about harvest timing need to be made.

**The goal of this project** is to build an intelligent assistant that:

1. Answers cultivation questions in natural language, grounded in a curated
   scientific and technical knowledge base
2. Reads live sensor data from the farmer's container and interprets it in context
3. Proactively alerts the farmer when parameters exceed safe thresholds
4. Will eventually predict growth trajectory and harvest readiness using trained
   ML models (Phase B)

---

## 2. System Architecture

The system is a multi-stage AI pipeline built with **LangGraph**, a framework for
constructing stateful decision graphs. Every user message passes through a
sequence of nodes, with conditional branches depending on intent and container
state.

### 2.1 Pipeline Overview

```
User message
    │
    ▼
check_container ──────── resolves whether a sensor container is linked
    │
    ▼
classify_intent ──────── LLM router classifies the user's goal
    │
    ├── confidence < 0.7  ──► request_clarification ──► END
    ├── OFF_DOMAIN        ──► reject_off_domain      ──► END
    ├── MEMORY_RECALL     ──► recall_memory          ──► END
    │
    ▼
retrieve_rag ─────────── hybrid BM25 + vector search, top-8 chunks
    │
    ├── no container ─────── generate_response (or reasoning_agent)
    │
    ├── has container
    │       │
    │       ▼
    │   run_ml_models ──── growth prediction, harvest readiness, anomaly
    │       │
    │       ▼
    │   read_sensors ───── live IoT readings
    │       │
    │       ├── HARVEST / SYSTEM ──► reasoning_agent  (deep analysis)
    │       └── KNOWLEDGE / UPDATE ► generate_response (fluent answer)
    │
    ▼
format_response ──────── assembles markdown: sensor card + alerts + answer
    │
    ▼
Browser / API response
```

### 2.2 Intent Labels

The intent classifier outputs one of six labels:

| Intent | Meaning | Example |
|--------|---------|---------|
| `KNOWLEDGE` | General cultivation question | "What pH is best for spirulina?" |
| `UPDATE` | Update or check container state | "What is my container status?" |
| `HARVEST` | Harvest timing and readiness | "Should I harvest today?" |
| `SYSTEM` | Multi-parameter system assessment | "Is my culture healthy?" |
| `OFF_DOMAIN` | Not about spirulina | "What is the weather?" |
| `MEMORY_RECALL` | User asks what was discussed | "What did we talk about?" |

---

## 3. Technical Components

### 3.1 Knowledge Base (RAG Pipeline)

**Document corpus:**
- 20+ source files: scientific papers, cultivation manuals, troubleshooting guides,
  FAQ pairs — in both French and English
- 5,356 text chunks after preprocessing and segmentation

**Embedding model:** `BAAI/bge-m3`
- Multilingual (handles French and English in the same index)
- 1,024-dimensional dense vectors
- Runs locally (no API cost, no data sent externally)

**Vector store:** ChromaDB (persistent, local)

**Retrieval strategy — Hybrid BM25 + Dense with RRF:**

Pure vector search retrieves semantically similar passages but can miss exact
keyword matches (parameter names, threshold values, species names). Pure BM25
keyword search misses semantic meaning. We fuse both using
**Reciprocal Rank Fusion (RRF)**:

```
score(chunk) = 1/(60 + dense_rank) + 1/(60 + bm25_rank)
```

Chunks that rank well in both lists rise to the top. This gives the best of
both retrieval paradigms. Top-8 chunks are passed to the generator.

### 3.2 Language Models

| Role | Model | Provider | Used for |
|------|-------|----------|---------- |
| Intent router | `llama-3.1-8b-instant` | Groq | Fast, cheap classification |
| Knowledge generator | `llama-3.3-70b-versatile` | Groq | Fluent expert answers |
| Reasoning agent | `nvidia/nemotron-120b` | OpenRouter | Complex sensor analysis |

Two separate LLMs are used for generation because the tasks are different:
- **KNOWLEDGE/UPDATE** questions need fluent, expert prose → Llama 70B
- **HARVEST/SYSTEM** questions need step-by-step analysis of sensor data + ML
  outputs → Nemotron 120B with chain-of-thought reasoning

The system prompt enforces seven behaviour rules: expert-first answering,
reserving "I don't know" for genuine gaps, sensor checks before dosing advice,
never guessing chemical doses, synthesising rather than quoting, escalating
critical situations, and asking one clarifying question at a time.

### 3.3 Proactive Monitoring

In addition to responding to user messages, the system monitors containers
**without being asked**:

- **APScheduler** runs a background check every 5 minutes
- Seven threshold rules are evaluated against live sensor readings:
  pH crash, pH too high, overheating, too cold, high salinity, low oxygen,
  harvest ready
- When a threshold is breached, the reasoning LLM generates a short plain-language
  alert (situation / what to do / consequence of inaction)
- Alerts are pushed to the browser in real time via **Server-Sent Events (SSE)**
- A deduplication mechanism prevents the same alert from firing repeatedly for the
  same ongoing condition

### 3.4 Response Formatting

The `format_response` node assembles the final output from several blocks:

- **Sensor status card** — parameter table with coloured status icons (✅ ⚠️ 🔴)
  based on OK/warning/critical ranges
- **Alert banners** — 🚨 CRITICAL / ⚠️ WARNING / 🌾 HARVEST when thresholds are
  breached
- **60-minute forecast table** — shows current and predicted values with trend
  arrows (Phase B)
- **Harvest window card** — three scenarios (early / balanced / optimal) with
  estimated yield (Phase B)
- **RAG answer** — grounded expert response with source footnotes

### 3.5 API and Frontend

- **Backend:** FastAPI (Python), single `/chat` endpoint, `/alerts/{user_id}` SSE
  stream, `/history/{user_id}` for session persistence
- **Frontend:** single-page HTML/CSS/JS chat interface with real-time alert
  injection from the SSE stream
- **Session memory:** conversation history is maintained per user and passed to
  the LLM on each request (last 10 turns)

---

## 4. Evaluation Results

### 4.1 RAG Quality (RAGAS Framework)

Evaluated on 30 questions across three categories using `llama-3.3-70b-versatile`
as both generator and judge.

| Category | Relevance | Faithfulness | Recall |
|----------|-----------|--------------|--------|
| Factual (10 Qs) | 0.730 | 0.930 | 0.700 |
| Troubleshooting (10 Qs) | 1.000 | 0.990 | 0.867 |
| Operational (10 Qs) | 0.900 | 0.883 | 0.733 |
| **Overall** | **0.873** | **0.942** | **0.767** |

All three metrics exceed the acceptance thresholds (relevance > 0.80, faithfulness
> 0.85, recall > 0.70). The pipeline is production-ready for the RAG component.

### 4.2 Intent Classification

- 30-scenario test suite covering all six intent labels
- **90%+ accuracy** using `llama-3.1-8b-instant`
- Confidence threshold (0.70) correctly triggers clarification for ambiguous inputs

### 4.3 Latency

Measured with a dedicated latency profiler across all pipeline stages:

| Stage | Time |
|-------|------|
| Embedding (BGE-M3) | ~80 ms |
| ChromaDB query | ~40 ms |
| BM25 retrieval | ~15 ms |
| LLM generation (70B) | ~280 ms |
| Formatting | ~5 ms |
| **Total (steady-state)** | **~430 ms** |

Target was under 3,000 ms. Achieved a **7× margin**. Cold start (model loading)
is handled by a pre-warm sequence at server startup.

### 4.4 Test Coverage

| Test suite | Tests | Result |
|------------|-------|--------|
| Unit tests (all pipeline nodes) | 92 | 92/92 pass |
| End-to-end conversation tests | 50 | 50/50 pass (90.7% quality score) |
| Intent router accuracy | 30 | 27/30 correct |

Unit tests cover every node without making real LLM or database calls (full
mocking), completing in ~4.5 seconds.

---

## 5. Phase B — ML Model Integration

The RAG agent is deliberately designed to accept ML model outputs through a single
integration point: the `ml_outputs` dictionary in the pipeline state. The
`run_ml_models` node is a placeholder that will be replaced with real model calls
in Phase B.

### 5.1 Models to Build

**Model 1 — Growth Prediction**
Predict OD680 (biomass proxy) 60 minutes ahead given the current sensor snapshot.
Output: `{current, in_60min, trend}` — rendered as a forecast table.

**Model 2 — Harvest Readiness**
Classify whether the culture should be harvested now, in 1 day, or in 2 days.
Output: three-scenario card with timing and estimated yield.

**Model 3 — Anomaly Detection**
Flag unusual sensor patterns that rule-based thresholds cannot catch
(e.g. abnormally fast pH drop, sensor drift, unusual OD-temperature co-trends).
Output: `anomaly_flag` (bool) + `anomaly_detail` (plain text description).

### 5.2 Data Strategy

Since real container logs are not yet available, Phase B begins with a
**physics-based simulator** derived from published *S. platensis* kinetic models
(Monod-type growth with light, temperature, and nutrient limitation).

The simulator generates realistic time-series with controlled anomaly injection,
providing unlimited labelled training data immediately.

Real container logging will run in parallel. Once 30+ full batch cycles
(~150 days of data) are collected, models will be retrained on real data.

### 5.3 Integration Path

```python
# run_ml_models node — Phase B body (no changes elsewhere in the graph)
from ml.growth   import predict_growth
from ml.harvest  import predict_harvest
from ml.anomaly  import detect_anomaly

sensor  = state["last_sensor_state"]
return {
    "ml_outputs": {
        "growth_prediction": predict_growth(sensor),
        "harvest_readiness": predict_harvest(sensor),
        "anomaly_flag":      detect_anomaly(sensor)[0],
        "anomaly_detail":    detect_anomaly(sensor)[1],
    }
}
```

The formatter and LLM prompts are already written to consume these keys.

---

## 6. Project Structure

```
Spirulina/
├── agent/
│   ├── graph.py            LangGraph pipeline definition
│   ├── nodes.py            All pipeline node functions
│   ├── intent_router.py    LLM-based intent classifier
│   ├── formatter.py        Markdown response templates
│   ├── monitor.py          Threshold rules + alert generator
│   ├── sensors.py          Sensor interface (mock → real IoT)
│   ├── memory.py           Conversation history (Redis / in-memory)
│   └── state.py            AgentState TypedDict schema
├── rag/
│   ├── retriever/
│   │   └── retrieve.py     Hybrid BM25 + ChromaDB retriever
│   └── generator/
│       └── generate.py     LLM answer generator
├── api/
│   └── main.py             FastAPI backend + SSE alerts
├── data/
│   ├── raw/                Source documents (PDFs, manuals, guides)
│   └── processed/chroma/   ChromaDB vector store (5,356 chunks)
├── tests/
│   ├── test_nodes_unit.py      92 unit tests (no LLM/DB calls)
│   ├── test_conversations.py   50 end-to-end scenarios
│   └── test_intent_router.py   30 intent classification cases
├── notebooks/
│   └── 02_growth_prediction.ipynb   Phase B model template
├── docs/
│   ├── phase_a_technical_note.md    Limitations and open questions
│   └── phase_b_ml_interface.md      ML model interface specification
└── chat.html               Single-page chat frontend
```

---

## 7. Summary

| Item | Status |
|------|--------|
| RAG knowledge base (5,356 chunks, FR+EN) | Complete |
| Hybrid retriever (BM25 + dense + RRF) | Complete |
| Intent classification (6 labels, 90%+ accuracy) | Complete |
| Dual-LLM generation pipeline | Complete |
| Proactive monitoring with SSE alerts | Complete |
| RAGAS evaluation (all metrics pass) | Complete |
| Unit + end-to-end test suite | Complete |
| ML model interface specification | Designed |
| Physics-based data simulator | Designed |
| Phase B ML models (growth, harvest, anomaly) | Phase B |
| Real IoT sensor integration | Phase B |
