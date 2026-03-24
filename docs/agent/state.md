# agent/state.py

## Purpose
Defines `AgentState` — the shared TypedDict that flows through every node in the LangGraph pipeline. Each node reads from it and returns a partial update.

## Schema

```python
class AgentState(TypedDict, total=False):
    # Identity / session
    user_id:           str        # who is asking
    container_id:      str        # linked grow container (empty = no container)
    has_container:     bool       # True if container_id is non-empty (set by check_container)

    # Intent classification
    intent:            str        # KNOWLEDGE | UPDATE | HARVEST | SYSTEM | UNKNOWN
    confidence:        float      # 0.0 – 1.0 from the intent router

    # RAG
    rag_context:       str        # formatted retrieved chunks for the LLM

    # ML model outputs
    ml_outputs:        dict       # growth_prediction, harvest_readiness, anomaly_flag, etc.

    # Conversation
    chat_history:      list[dict] # [{role: "user"|"assistant", content: str}, ...]
                                  # Annotated with operator.add — appends on merge

    # Hardware / IoT
    last_sensor_state: dict       # latest sensor readings from get_sensor_reading()

    # Final answer
    response:          str        # the final formatted markdown response
```

## Important note on `chat_history`
It uses `Annotated[list[dict], operator.add]` — this means when a node returns a partial `chat_history`, LangGraph **appends** it to the existing list rather than replacing it. Nodes that add to history (like `request_clarification` and `format_response`) return only the new messages.

## `total=False`
All fields are optional. Nodes only need to include the keys they update in their return dict.

## Dependencies
- `typing_extensions.TypedDict`
- `typing.Annotated`
- `operator.add` (for chat_history merge strategy)
