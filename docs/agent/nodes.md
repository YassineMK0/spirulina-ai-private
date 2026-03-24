# agent/nodes.py

## Purpose
Contains all LangGraph node functions — one per pipeline stage. Each function receives the full `AgentState` dict and returns a partial dict with only the keys it updates. LangGraph merges the update into the running state automatically.

## Nodes

### `check_container`
Sets `container_id` and `has_container` (bool) from state. Entry point of the pipeline.

### `retrieve_rag`
Calls `rag.retriever.retrieve.retrieve()` with top_k=8 (hybrid BM25+dense).
Uses `_retrieval_query()` which detects follow-up messages (pronouns like "ça", "it", "this") and prepends the previous user turn to the query for better context.

### `run_ml_models`
Placeholder for ML inference (growth prediction, anomaly detection). Currently passes through `ml_outputs` from state. Replace with real model calls when ML models are trained.

### `read_sensors`
Calls `agent.sensors.get_sensor_reading(container_id)`. Currently returns mock data. Replace with real IoT API call.

### `reasoning_agent` ← **NEW (dual-LLM)**
Called for **HARVEST** and **SYSTEM** intents. Uses `rag.generator.reasoning_generate()` which calls **DeepSeek R1** (`deepseek-r1-distill-llama-70b`) via Groq.

DeepSeek R1 outputs `<think>...</think>` chain-of-thought blocks — these are stripped before the answer reaches the user.

Use cases:
- Harvest timing decisions (OD analysis, yield estimation, self-shading risk)
- Anomaly/sensor diagnosis (root cause, priority actions)

### `generate_response`
Called for **KNOWLEDGE** and **UPDATE** intents. Uses `rag.generator.generate_answer()` which calls **Llama 3.3 70b** via Groq. Optimised for fluent, grounded prose following the 7 behavior rules.

### `request_clarification`
Triggered when intent confidence < 0.7. Scans the message for keyword hints (harvest, pH, contamination, etc.) and asks one targeted clarifying question.

### `reject_off_domain`
Triggered when intent = OFF_DOMAIN. Returns a polite one-line redirect without touching RAG.

### `recall_memory`
Triggered when intent = MEMORY_RECALL. Reads `chat_history` from state and formats past turns into a readable summary. Zero LLM calls, zero RAG.

### `format_response`
Final node for all non-early-exit paths. Calls `agent.formatter.format_message()` which selects and combines markdown templates (sensor card, harvest card, prediction table, alert banners) based on intent and available data.

## Helper functions

### `_last_user_message(state)`
Returns the most recent message where `role == "user"` from `chat_history`.

### `_retrieval_query(state)`
Context-aware query builder. If the current message is short (<10 words) or contains pronouns (FR+EN list), prepends the previous user turn to improve retrieval quality on follow-up questions.
