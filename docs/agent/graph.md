# agent/graph.py

## Purpose
Defines and compiles the LangGraph pipeline. Wires all nodes together with edges and conditional routing gates.

## Full pipeline

```
check_container
      |
classify_intent
      |
_route_after_classify
   |-- confidence < 0.7       -> request_clarification -> END
   |-- intent = OFF_DOMAIN    -> reject_off_domain      -> END
   |-- intent = MEMORY_RECALL -> recall_memory          -> END
   +-- else                   -> retrieve_rag
                                      |
                               _post_rag_gate
                     |------------------+---------------------|
              has_container=True                         no container
                     |                         |----------------+----------------|
              run_ml_models             HARVEST/SYSTEM                  KNOWLEDGE/UPDATE
                     |                         |                                 |
              read_sensors              reasoning_agent                 generate_response
                     |                         |                                 |
           _post_sensors_gate          format_response -> END          format_response -> END
        |---------------------|
  HARVEST/SYSTEM        KNOWLEDGE/UPDATE
        |                     |
  reasoning_agent       generate_response
        |                     |
  format_response -> END  format_response -> END
```

## Routing gates

### `_route_after_classify`
Three early exits before RAG is touched:
- Low confidence (< 0.7) -> clarification
- OFF_DOMAIN -> polite redirect
- MEMORY_RECALL -> pull from chat history

### `_post_rag_gate`
After `retrieve_rag`. Decides ML+sensors path:
- `has_container=True` -> run ML + sensors
- `has_container=False` + HARVEST/SYSTEM -> straight to `reasoning_agent`
- `has_container=False` + KNOWLEDGE/UPDATE -> straight to `generate_response`

### `_post_sensors_gate`
After `read_sensors` (container path only). Selects the generator:
- HARVEST or SYSTEM -> `reasoning_agent` (Nemotron 120B — step-by-step)
- KNOWLEDGE or UPDATE -> `generate_response` (Llama 3.3 70b — fluent prose)

## Dual-LLM routing summary

| Intent | Has container | Generator |
|--------|--------------|-----------|
| KNOWLEDGE | any | Llama 3.3 70b (Groq) |
| UPDATE | any | Llama 3.3 70b (Groq) |
| HARVEST | no | Nemotron 120B (OpenRouter) |
| HARVEST | yes | Nemotron 120B + sensor + ML |
| SYSTEM | no | Nemotron 120B (OpenRouter) |
| SYSTEM | yes | Nemotron 120B + sensor + ML |

## Key constants
- `CONFIDENCE_THRESHOLD = 0.7` (imported from `intent_router`)
- `_REASONING_INTENTS = {"HARVEST", "SYSTEM"}`
