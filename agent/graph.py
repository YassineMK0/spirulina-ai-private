"""LangGraph graph definition.

Pipeline order
--------------
1. check_container    - resolve container_id / has_container
2. classify_intent    - LLM router -> JSON { intent, confidence }
                        (runs for ALL users, container or not)
3. confidence gate    - if confidence < 0.7 -> request_clarification -> END
4. retrieve_rag       - vector-store lookup (runs for ALL users)
5. ML gate            - split on has_container:
     has_container=True  -> run_ml_models -> read_sensors -> generate_response
     has_container=False -> generate_response  (RAG-only + friendly message)
6. format_response    - wrap raw LLM answer in markdown template (all paths)

Run directly to smoke-test:
    python -m agent.graph
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.intent_router import classify_intent, CONFIDENCE_THRESHOLD
from agent.nodes import (
    check_container,
    format_response,
    generate_response,
    read_sensors,
    request_clarification,
    retrieve_rag,
    run_ml_models,
)
from agent.state import AgentState


# -- gate: low confidence → ask user to rephrase ---------------------------
def _confidence_gate(state: AgentState) -> str:
    if state.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD:
        return "retrieve_rag"
    return "request_clarification"


# -- gate: split full pipeline vs RAG-only after vector search -------------
def _ml_gate(state: AgentState) -> str:
    """Full pipeline only when a container is linked."""
    if state.get("has_container"):
        return "run_ml_models"
    return "generate_response"


# -- build graph -----------------------------------------------------------
builder = StateGraph(AgentState)

builder.add_node("check_container", check_container)
builder.add_node("classify_intent", classify_intent)
builder.add_node("request_clarification", request_clarification)
builder.add_node("retrieve_rag", retrieve_rag)
builder.add_node("run_ml_models", run_ml_models)
builder.add_node("read_sensors", read_sensors)
builder.add_node("generate_response", generate_response)
builder.add_node("format_response", format_response)

# check_container always proceeds to intent classification
builder.set_entry_point("check_container")
builder.add_edge("check_container", "classify_intent")

# intent classification → confidence gate
builder.add_conditional_edges(
    "classify_intent",
    _confidence_gate,
    {
        "retrieve_rag": "retrieve_rag",
        "request_clarification": "request_clarification",
    },
)

builder.add_edge("request_clarification", END)

# after RAG → ML gate splits full vs RAG-only
builder.add_conditional_edges(
    "retrieve_rag",
    _ml_gate,
    {
        "run_ml_models": "run_ml_models",
        "generate_response": "generate_response",
    },
)

builder.add_edge("run_ml_models", "read_sensors")
builder.add_edge("read_sensors", "generate_response")
builder.add_edge("generate_response", "format_response")
builder.add_edge("format_response", END)

graph = builder.compile()

# -- smoke-test when executed directly -------------------------------------
if __name__ == "__main__":
    import os
    from unittest.mock import MagicMock, patch
    from dotenv import load_dotenv
    load_dotenv()

    MOCK_CHAIN = MagicMock()
    MOCK_CHAIN.invoke.return_value = '{"intent": "KNOWLEDGE", "confidence": 0.95}'

    with patch("agent.intent_router._get_chain", return_value=MOCK_CHAIN):

        # --- Test 1: no container -> RAG-only path ------------------------
        print("=== Test 1: no container (RAG-only + friendly message) ===")
        result1 = graph.invoke({
            "user_id": "user-no-container",
            "container_id": "",
            "chat_history": [{"role": "user", "content": "What pH is best for spirulina?"}],
        })
        for k, v in result1.items():
            print(f"  {k}: {v!r}")
        assert result1["has_container"] is False
        assert result1["intent"] == "KNOWLEDGE"
        assert result1.get("response", "") != ""
        print("  PASS: RAG-only path, response generated\n")

        # --- Test 2: with container -> full pipeline ----------------------
        print("=== Test 2: with container (full pipeline: RAG + ML + sensors) ===")
        result2 = graph.invoke({
            "user_id": "user-with-container",
            "container_id": "container-42",
            "chat_history": [{"role": "user", "content": "What pH is best for spirulina?"}],
        })
        for k, v in result2.items():
            print(f"  {k}: {v!r}")
        assert result2["has_container"] is True
        assert result2["intent"] == "KNOWLEDGE"
        assert result2.get("response", "") != ""
        print("  PASS: full pipeline ran (ML + sensors + format nodes executed)\n")

        # --- Test 3: low confidence -> clarification ----------------------
        print("=== Test 3: low confidence -> request_clarification ===")
        MOCK_CHAIN.invoke.return_value = '{"intent": "UNKNOWN", "confidence": 0.45}'
        result3 = graph.invoke({
            "user_id": "user-with-container",
            "container_id": "container-42",
            "chat_history": [{"role": "user", "content": "uh idk do the thing"}],
        })
        for k, v in result3.items():
            print(f"  {k}: {v!r}")
        assert result3["confidence"] < CONFIDENCE_THRESHOLD
        assert "rephrase" in result3["response"].lower()
        print("  PASS: clarification node triggered\n")

    print("All smoke tests passed.")
