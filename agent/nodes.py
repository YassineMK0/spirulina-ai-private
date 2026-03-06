"""LangGraph node functions — one per pipeline stage.

Each function receives the full AgentState dict and returns a partial
dict with the keys it wants to update.  LangGraph merges the update
into the running state automatically.
"""

from __future__ import annotations

from typing import Any

from agent.state import AgentState


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

# Pronouns/demonstratives that signal a follow-up question (FR + EN)
_FOLLOW_UP_TOKENS = {
    # French
    "ça", "ca", "cela", "ceci", "ce", "cette", "ces", "il", "elle", "ils", "elles",
    "lui", "leur", "y", "en", "lequel", "laquelle", "lesquels", "lesquelles",
    # English
    "it", "its", "this", "that", "these", "those", "they", "them", "their",
    "he", "she", "we", "our", "such",
}


def _last_user_message(state: AgentState) -> str:
    """Return the most recent user message from chat_history."""
    for msg in reversed(state.get("chat_history", [])):
        if msg.get("role") == "user":
            return msg.get("content", "").strip()
    return ""


def _retrieval_query(state: AgentState) -> str:
    """Build a context-aware retrieval query.

    If the current message is a short follow-up (contains pronouns like
    "ça", "it", "this", etc.), prepend the previous user message so the
    retriever understands what the pronoun refers to.

    Example:
        Turn 1 user: "What causes spirulina to turn yellow?"
        Turn 2 user: "comment le pH affecte ça"
        Retrieval query: "What causes spirulina to turn yellow? | comment le pH affecte ça"
    """
    current = _last_user_message(state)
    history = state.get("chat_history", [])

    tokens = set(current.lower().split())
    is_short      = len(current.split()) < 10
    has_pronoun   = bool(tokens & _FOLLOW_UP_TOKENS)

    if (is_short or has_pronoun) and len(history) >= 2:
        # Collect previous user messages (exclude the current one)
        prev_user = [
            m["content"] for m in history[:-1]
            if m.get("role") == "user"
        ]
        if prev_user:
            print(f"  [retrieval] follow-up detected — augmenting query with previous turn")
            return f"{prev_user[-1]} | {current}"

    return current


def check_container(state: AgentState) -> dict[str, Any]:
    """Stage 2 — resolve whether a grow-container is linked."""
    print("[node] check_container")
    return {
        "container_id": state.get("container_id") or "",
        "has_container": bool(state.get("container_id")),
    }


def retrieve_rag(state: AgentState) -> dict[str, Any]:
    """Stage 3 — pull relevant knowledge from the vector store."""
    print("[node] retrieve_rag")
    try:
        from rag.retriever.retrieve import retrieve, format_context
        query = _retrieval_query(state)
        print(f"  [retrieval] query: {query[:120]}")
        chunks = retrieve(query, top_k=5)
        context = format_context(chunks)
    except Exception as exc:
        print(f"  [warn] RAG retrieval failed: {exc}")
        context = ""
    return {"rag_context": context}


def run_ml_models(state: AgentState) -> dict[str, Any]:
    """Stage 4 — execute ML inference (growth prediction, anomaly, etc.)."""
    print("[node] run_ml_models")
    return {"ml_outputs": state.get("ml_outputs") or {}}


def read_sensors(state: AgentState) -> dict[str, Any]:
    """Stage 5 — fetch latest sensor telemetry."""
    print("[node] read_sensors")
    return {"last_sensor_state": state.get("last_sensor_state") or {}}


def request_clarification(state: AgentState) -> dict[str, Any]:
    """Triggered when intent confidence < 0.7.

    Asks the user to rephrase so the router can try again.
    """
    intent = state.get("intent", "UNKNOWN")
    confidence = state.get("confidence", 0.0)
    print(f"[node] request_clarification  (intent={intent}, confidence={confidence:.2f})")
    return {
        "response": (
            f"I'm not confident enough about what you need "
            f"(best guess: {intent}, confidence: {confidence:.0%}). "
            f"Could you rephrase your question?"
        ),
        "chat_history": [
            {
                "role": "assistant",
                "content": "Could you rephrase? I want to make sure I help you correctly.",
            }
        ],
    }


def generate_response(state: AgentState) -> dict[str, Any]:
    """Stage 6 — call the LLM and store the raw answer in state.

    Does NOT write chat_history — that is handled by format_response
    so the conversation log always contains the final formatted message.
    """
    print("[node] generate_response")

    from rag.generator.generate import generate_answer

    question      = _last_user_message(state)
    context       = state.get("rag_context", "")
    history       = state.get("chat_history", [])
    has_container = state.get("has_container", False)

    sensor_state = state.get("last_sensor_state") if has_container else None
    ml_outputs   = state.get("ml_outputs")        if has_container else None

    answer = generate_answer(
        question=question,
        context=context,
        history=history,
        sensor_state=sensor_state,
        ml_outputs=ml_outputs,
    )

    return {"response": answer}


def format_response(state: AgentState) -> dict[str, Any]:
    """Stage 7 — wrap the raw LLM answer in the appropriate markdown template.

    Selects and combines templates based on intent, has_container, and
    which data (sensor / ML) is actually present in state.
    """
    print("[node] format_response")

    from agent.formatter import format_message

    formatted = format_message(
        raw_answer    = state.get("response", ""),
        intent        = state.get("intent", "KNOWLEDGE"),
        has_container = state.get("has_container", False),
        rag_context   = state.get("rag_context", ""),
        sensor        = state.get("last_sensor_state") or {},
        ml_outputs    = state.get("ml_outputs") or {},
        container_id  = state.get("container_id", ""),
    )

    return {
        "response": formatted,
        "chat_history": [{"role": "assistant", "content": formatted}],
    }
