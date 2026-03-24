# rag/generator/generate.py

## Purpose
The RAG answer generator. Takes a question, retrieved context, conversation history, and optional sensor/ML data, and calls the LLM to produce a grounded spirulina expert answer.

## Dual-LLM architecture

Two generators, selected by intent in `agent/graph.py`:

| Function | Model | Intent | Style |
|----------|-------|--------|-------|
| `generate_answer()` | Llama 3.3 70b | KNOWLEDGE, UPDATE | Fluent expert prose |
| `reasoning_generate()` | DeepSeek R1 70b | HARVEST, SYSTEM | Step-by-step analysis |

Both are Groq-hosted. Both use separate `lru_cache` singletons so they load once and reuse.

## `generate_answer()`
Standard RAG generator for knowledge and update questions.

- **Model:** `llama-3.3-70b-versatile` (configurable via `GENERATOR_MODEL_NAME`)
- **Temperature:** 0.2 — slight warmth for natural tone
- **Max tokens:** 1024
- **System prompt:** 7 behavior rules (EXPERT FIRST, NO DASHBOARD, SENSOR BEFORE DOSING, etc.)
- **Fallback:** Returns `_NO_CONTEXT_ANSWER` if ChromaDB context is empty — no LLM call made

## `reasoning_generate()`
Step-by-step analysis for harvest decisions and system/anomaly diagnosis.

- **Model:** `deepseek-r1-distill-llama-70b` (configurable via `REASONING_MODEL_NAME`, always Groq)
- **Temperature:** 0.1 — low for consistent reasoning
- **Max tokens:** 2048 — R1 needs room for its reasoning chain
- **System prompt:** Structured reasoning protocol (harvest = 5-step OD analysis; system = 5-step anomaly diagnosis)
- **Think-tag stripping:** `_strip_think_tags()` removes `<think>...</think>` blocks from R1 output before returning

## Configuration (env vars)

| Variable | Default | Description |
|----------|---------|-------------|
| `GENERATOR_MODEL_PROVIDER` | `groq` | Provider for `generate_answer` |
| `GENERATOR_MODEL_NAME` | `llama-3.3-70b-versatile` | Model for `generate_answer` |
| `REASONING_MODEL_NAME` | `deepseek-r1-distill-llama-70b` | Model for `reasoning_generate` (always Groq) |

## Helper functions

| Function | Purpose |
|----------|---------|
| `_format_history(history, window=6)` | Converts last 6 messages to readable text |
| `_format_sensor_block(sensor)` | Wraps sensor dict in `<sensor_readings>` XML tags |
| `_format_ml_block(ml)` | Wraps ML outputs in `<ml_predictions>` XML tags |
| `_strip_think_tags(text)` | Removes DeepSeek R1 `<think>...</think>` blocks |
| `get_generator_chain()` | Returns cached Llama chain |
| `get_reasoning_chain()` | Returns cached DeepSeek R1 chain |
