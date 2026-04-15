# SpirulinaAI — Phase A Technical Note

**Status:** Production-ready RAG agent, locked for Phase B ML integration  
**Date:** 2026-03-31

---

## What the agent does

SpirulinaAI is a domain-expert chat assistant for *Spirulina platensis* farmers.
It runs a LangGraph pipeline that classifies the user's intent, retrieves relevant
cultivation knowledge, optionally reads IoT sensor data and ML model outputs, then
generates a grounded, actionable response.

**Pipeline stages (in order):**

```
check_container
  → classify_intent          (Llama 3.1 8b, Groq, JSON router)
  → [clarify | off-domain | memory | retrieve_rag]
  → retrieve_rag             (BM25 + ChromaDB dense, RRF fusion, top-8)
  → [run_ml_models → read_sensors]   (only when container linked)
  → [reasoning_agent | generate_response]
       reasoning: Nemotron 120b via OpenRouter  (HARVEST / SYSTEM intents)
       generate:  Llama 3.3 70b via Groq        (KNOWLEDGE / UPDATE intents)
  → format_response          (markdown template combiner)
```

**Six intent labels:** KNOWLEDGE · UPDATE · HARVEST · SYSTEM · OFF_DOMAIN · MEMORY_RECALL

**RAG corpus:** 5 356 chunks across 20+ files (French + English PDFs, manuals, QA pairs,
troubleshooting guides), embedded with `BAAI/bge-m3` (1 024 dims, multilingual).

**Proactive monitor:** APScheduler fires every 5 min, checks hard-coded thresholds
against live sensor readings, pushes SSE alerts to the browser without user input.

---

## What is working well

| Area | Result |
|------|--------|
| RAG quality (final eval, 70b judge) | relevance 0.87 · faithfulness 0.94 · recall 0.77 |
| Intent classification accuracy | 90 %+ on 30-scenario test suite (8b model) |
| End-to-end latency (steady-state) | ~430 ms (target < 3 000 ms) |
| Unit test coverage | 92 tests, 0 failures, pure-unit (no LLM/DB calls) |
| End-to-end conversation tests | 50/50 pass, 90.7 % quality score |
| Proactive alerting | SSE delivery confirmed, dedup on breach labels |

---

## Known limitations

### 1. ML placeholder — `run_ml_models` is a no-op

The graph calls `run_ml_models` on every request with a container, but the node
returns the existing `ml_outputs` unchanged (usually `{}`).
Until Phase B delivers real models, the forecast table, harvest window, and anomaly
banners in the formatter never fire. The agent is answering from RAG alone.

### 2. Sensors are simulated

`agent/sensors.py` returns hard-coded or seeded-random readings.
No live IoT integration exists. The monitor's 5-minute threshold checks run
against these fakes — useful for testing but not production data.

### 3. Threshold rules are hand-coded

`agent/monitor.py` uses seven static rules (pH < 7.5, OD > 1.1, etc.).
These will be superseded by the anomaly-detection model in Phase B, but until
then a mis-tuned threshold will silently miss or flood alerts.

### 4. Groq token quota

`llama-3.3-70b-versatile` has a 100 k token/day free-tier cap.
A busy day (many long conversations or a full RAGAS eval run) exhausts the
quota. A second API key is in `.env` as a fallback, but rotation is manual.

### 5. No persistent session store

`chat_history` lives in the HTTP request payload, sent by the frontend each
time. Long conversations bloat request size; there is no server-side memory or
summarisation. Losing the browser tab loses the conversation.

### 6. French corpus quality gap

Factual and troubleshooting recall is strong. Operational recall (0.77) is
weaker partly because several French PDFs use non-standard terminology and the
chunker sometimes splits mid-sentence across headings.

---

## Open questions

1. **Real sensor API shape** — When the IoT hardware is ready, what protocol
   (REST / MQTT / WebSocket) and what exact key names will it use?
   The mock schema in `sensors.py` is the contract; any deviation requires a
   thin adapter layer.

2. **Training data source** — Do we build a physics-based simulator or collect
   from real containers? Simulator allows controlled anomaly injection;
   real data has distribution fidelity. See Phase B plan.

3. **Model serving** — Will ML models run in-process (joblib/ONNX) or as a
   separate microservice? In-process is simpler; a microservice allows
   independent scaling and language-agnostic training.

4. **Harvest ground truth** — OD680 is used as the biomass proxy, but actual
   dry-weight yield depends on centrifuge efficiency and drying method. Should
   the harvest model predict OD or dry weight?

5. **Multi-container scaling** — The monitor currently holds sessions in a
   Python dict (lost on restart). For multiple concurrent users and containers,
   a Redis-backed session store is needed.

6. **LLM cost at scale** — OpenRouter Nemotron (reasoning path) has no hard
   token cap but will incur cost at production volume. What is the acceptable
   cost per conversation?
