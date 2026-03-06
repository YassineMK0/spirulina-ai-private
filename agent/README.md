# agent/ — LangGraph Pipeline

The core AI pipeline. Defines the state schema, all processing nodes,
and the graph that wires them together.

---

## Files

### `state.py`
Shared state schema (`AgentState` TypedDict) passed between every node.

| Field | Type | Set by |
|---|---|---|
| `user_id` | str | caller |
| `container_id` | str | caller / check_container |
| `has_container` | bool | check_container |
| `intent` | str | classify_intent |
| `confidence` | float | classify_intent |
| `rag_context` | str | retrieve_rag |
| `ml_outputs` | dict | run_ml_models |
| `chat_history` | list[dict] | every node (append-only) |
| `last_sensor_state` | dict | read_sensors |
| `response` | str | generate_response |

`chat_history` uses `Annotated[list, operator.add]` — LangGraph appends
new messages rather than overwriting the whole list.

---

### `graph.py`
Compiles the `StateGraph` and exports the runnable `graph` object.

```
check_container
      |
classify_intent
      |
   [confidence gate]
   >= 0.7              < 0.7
      |                   |
retrieve_rag     request_clarification --> END
      |
   [ml gate]
has_container=True    has_container=False
      |                       |
run_ml_models          generate_response --> END
      |
read_sensors
      |
generate_response --> END
```

Two conditional edges:
- **confidence gate** (after `classify_intent`): routes to clarification if
  the router is unsure (confidence < 0.7).
- **ml gate** (after `retrieve_rag`): full pipeline for container users,
  RAG-only for users without a linked container.

---

### `intent_router.py`
LLM-backed intent classifier. Calls Groq `llama-3.1-8b-instant`.

Returns `{"intent": "KNOWLEDGE", "confidence": 0.95}`.

Valid intents: `KNOWLEDGE` | `UPDATE` | `HARVEST` | `SYSTEM`

Supports switching provider via env vars:
```
INTENT_MODEL_PROVIDER=groq   # groq | openai | ollama
INTENT_MODEL_NAME=llama-3.1-8b-instant
```

Tested: **90% accuracy on 30-message eval set** (27/30 correct).

---

### `nodes.py`
One function per pipeline stage. Each receives `AgentState`, returns a
partial dict that LangGraph merges into the running state.

| Node | Status | Does |
|---|---|---|
| `check_container` | Done | Sets `has_container` from `container_id` |
| `classify_intent` | Done | Calls intent_router, sets `intent` + `confidence` |
| `retrieve_rag` | Done | Queries ChromaDB top-5, sets `rag_context` |
| `run_ml_models` | Placeholder | Will run growth/anomaly/harvest ML models |
| `read_sensors` | Placeholder | Will fetch live IoT sensor telemetry |
| `generate_response` | Done | Calls LLM generator, sets `response` |
| `request_clarification` | Done | Returns rephrase prompt when confidence < 0.7 |

---

## Running

```python
from agent.graph import graph

result = graph.invoke({
    "chat_history": [{"role": "user", "content": "What pH should I target?"}],
    "container_id": "CTR-001",   # omit for RAG-only mode
})
print(result["response"])
```
