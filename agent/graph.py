"""LangGraph graph definition.

Pipeline order
--------------
1. check_container       - resolve container_id / has_container
2. classify_intent       - LLM router -> JSON { intent, confidence }
                           (runs for ALL users, container or not)
3. routing gate          - branches based on intent + confidence:
     confidence < 0.7    -> request_clarification  -> END
     intent=OFF_DOMAIN   -> reject_off_domain       -> END
     intent=MEMORY_RECALL-> recall_memory           -> END
     otherwise           -> retrieve_rag
4. retrieve_rag          - vector-store lookup (runs for all normal paths)
5. post-RAG gate         - split on has_container + intent:
     has_container=True  -> run_ml_models -> read_sensors -> post-sensors gate
     HARVEST/SYSTEM (no container) -> reasoning_agent
     otherwise (no container)      -> generate_response
6. post-sensors gate     - split on intent after sensor data is available:
     HARVEST / SYSTEM    -> reasoning_agent  (DeepSeek R1 — step-by-step)
     KNOWLEDGE / UPDATE  -> generate_response (Llama 3.3 70b — fluent prose)
7. format_response       - wrap raw LLM answer in markdown template

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
    reasoning_agent,
    recall_memory,
    reject_off_domain,
    request_clarification,
    retrieve_rag,
    run_ml_models,
)
from agent.state import AgentState


# -- gate: route after classification --------------------------------------
def _route_after_classify(state: AgentState) -> str:
    """Branch based on confidence threshold and intent type."""
    if state.get("confidence", 0.0) < CONFIDENCE_THRESHOLD:
        return "request_clarification"
    intent = state.get("intent", "UNKNOWN")
    if intent == "OFF_DOMAIN":
        return "reject_off_domain"
    if intent == "MEMORY_RECALL":
        return "recall_memory"
    return "retrieve_rag"


_REASONING_INTENTS = {"HARVEST", "SYSTEM"}


# -- gate: after RAG — route by container + intent -------------------------
def _post_rag_gate(state: AgentState) -> str:
    """Run ML+sensors when container exists; otherwise split by intent."""
    if state.get("has_container"):
        return "run_ml_models"
    if state.get("intent", "KNOWLEDGE").upper() in _REASONING_INTENTS:
        return "reasoning_agent"
    return "generate_response"


# -- gate: after sensors — choose generator by intent ---------------------
def _post_sensors_gate(state: AgentState) -> str:
    """HARVEST/SYSTEM -> DeepSeek R1 reasoning; everything else -> Llama 70b."""
    if state.get("intent", "KNOWLEDGE").upper() in _REASONING_INTENTS:
        return "reasoning_agent"
    return "generate_response"


# -- build graph -----------------------------------------------------------
builder = StateGraph(AgentState)

builder.add_node("check_container",      check_container)
builder.add_node("classify_intent",      classify_intent)
builder.add_node("request_clarification",request_clarification)
builder.add_node("reject_off_domain",    reject_off_domain)
builder.add_node("recall_memory",        recall_memory)
builder.add_node("retrieve_rag",         retrieve_rag)
builder.add_node("run_ml_models",        run_ml_models)
builder.add_node("read_sensors",         read_sensors)
builder.add_node("reasoning_agent",      reasoning_agent)
builder.add_node("generate_response",    generate_response)
builder.add_node("format_response",      format_response)

# check_container → intent classification
builder.set_entry_point("check_container")
builder.add_edge("check_container", "classify_intent")

# intent classification → routing gate
builder.add_conditional_edges(
    "classify_intent",
    _route_after_classify,
    {
        "retrieve_rag":          "retrieve_rag",
        "request_clarification": "request_clarification",
        "reject_off_domain":     "reject_off_domain",
        "recall_memory":         "recall_memory",
    },
)

builder.add_edge("request_clarification", END)
builder.add_edge("reject_off_domain",      END)
builder.add_edge("recall_memory",          END)

# after RAG → post-RAG gate (container + intent aware)
builder.add_conditional_edges(
    "retrieve_rag",
    _post_rag_gate,
    {
        "run_ml_models":    "run_ml_models",
        "reasoning_agent":  "reasoning_agent",
        "generate_response":"generate_response",
    },
)

# after ML+sensors → choose generator by intent
builder.add_edge("run_ml_models", "read_sensors")
builder.add_conditional_edges(
    "read_sensors",
    _post_sensors_gate,
    {
        "reasoning_agent":  "reasoning_agent",
        "generate_response":"generate_response",
    },
)

# both generators → format → END
builder.add_edge("reasoning_agent",   "format_response")
builder.add_edge("generate_response", "format_response")
builder.add_edge("format_response",   END)

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
        assert result3.get("response", "") != ""
        print("  PASS: clarification node triggered\n")

    print("All smoke tests passed.")
