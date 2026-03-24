"""LangGraph node functions — one per pipeline stage.

Each function receives the full AgentState dict and returns a partial
dict with the keys it wants to update.  LangGraph merges the update
into the running state automatically.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from agent.state import AgentState


# ---------------------------------------------------------------------------
# Shared helpers
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

# Threshold above which a query is "very long" and should be summarized
# for retrieval (the full text still goes to the LLM generator).
LONG_QUERY_THRESHOLD = 400   # characters

# Keyword hints used to ask a targeted clarifying question
_CLARIFY_HINTS: list[tuple[set[str], str]] = [
    (
        {"harvest", "récolte", "ready", "prêt", "when", "quand"},
        "Are you asking about **harvest timing** (when to harvest based on OD) "
        "or about **harvest procedures** (how to do it step by step)?",
    ),
    (
        {"ph", "acid", "alcalin", "bicarbonate", "drop", "rise", "chute", "monte"},
        "Are you asking about **adjusting pH manually**, or about **understanding "
        "what's causing your pH to drift**?",
    ),
    (
        {"nutrient", "nutriment", "fertiliz", "dose", "feed", "add", "ajouter"},
        "Are you asking **how much to add right now**, or about the "
        "**general nutrient schedule**?",
    ),
    (
        {"grow", "growth", "croissance", "slow", "lent", "produc", "biomass"},
        "Are you **troubleshooting slow growth**, or asking about "
        "**expected growth rates in general**?",
    ),
    (
        {"contaminat", "color", "couleur", "smell", "odeur", "green", "vert", "yellow", "jaune"},
        "Are you seeing a **specific change in your culture right now**, "
        "or asking about **contamination prevention**?",
    ),
]


def _last_user_message(state: AgentState) -> str:
    """Return the most recent user message from chat_history."""
    for msg in reversed(state.get("chat_history", [])):
        if msg.get("role") == "user":
            return msg.get("content", "").strip()
    return ""


@lru_cache(maxsize=1)
def _get_summarizer_chain():
    """Lazy singleton chain that compresses a long query into a short retrieval query."""
    import os
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    llm = ChatGroq(
        model=os.getenv("INTENT_MODEL_NAME", "llama-3.1-8b-instant"),
        temperature=0,
        max_tokens=60,
    )
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "Compress the following spirulina cultivation question into a concise "
            "retrieval query of 15 words or fewer, keeping the key topic. "
            "Reply with only the query — no explanation.",
        ),
        ("human", "{question}"),
    ])
    return prompt | llm | StrOutputParser()


def _summarize_long_query(text: str) -> str:
    """Summarize a very long question into a short retrieval query (≤15 words)."""
    try:
        result = _get_summarizer_chain().invoke({"question": text})
        return result.strip()
    except Exception:
        return text[:200]   # graceful fallback: truncate


def _retrieval_query(state: AgentState) -> str:
    """Build a context-aware retrieval query.

    1. Very long query (>400 chars): summarize with fast LLM for retrieval.
    2. Short follow-up with pronouns: prepend previous user turn for context.
    3. Normal: return as-is.
    """
    current = _last_user_message(state)
    history = state.get("chat_history", [])

    # Edge case 4: very long question — summarize before retrieval
    if len(current) > LONG_QUERY_THRESHOLD:
        print(f"  [retrieval] long query ({len(current)} chars) — summarizing")
        summarized = _summarize_long_query(current)
        print(f"  [retrieval] summary: {summarized[:100]}")
        return summarized

    # Follow-up detection: short message or contains reference pronouns
    tokens = set(current.lower().split())
    is_short    = len(current.split()) < 10
    has_pronoun = bool(tokens & _FOLLOW_UP_TOKENS)

    if (is_short or has_pronoun) and len(history) >= 2:
        prev_user = [
            m["content"] for m in history[:-1]
            if m.get("role") == "user"
        ]
        if prev_user:
            print("  [retrieval] follow-up detected — augmenting query with previous turn")
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
        chunks = retrieve(query, top_k=8)
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
    container_id = state.get("container_id") or ""
    if not container_id:
        return {"last_sensor_state": {}}
    try:
        from agent.sensors import get_sensor_reading
        reading = get_sensor_reading(container_id)
        print(f"  [sensors] got reading for container={container_id}: status={reading.get('status')}")
        return {"last_sensor_state": reading}
    except Exception as exc:
        print(f"  [warn] sensor read failed: {exc}")
        return {"last_sensor_state": {}}


def reasoning_agent(state: AgentState) -> dict[str, Any]:
    """Reasoning stage — DeepSeek R1 for HARVEST and SYSTEM intents.

    Called instead of generate_response when the intent requires step-by-step
    analysis: harvest timing decisions, anomaly diagnosis, sensor interpretation.
    Strips DeepSeek's <think> tags so only the final answer reaches the user.
    """
    print("[node] reasoning_agent  (DeepSeek R1)")

    from rag.generator.generate import reasoning_generate

    question      = _last_user_message(state)
    context       = state.get("rag_context", "")
    history       = state.get("chat_history", [])
    has_container = state.get("has_container", False)

    sensor_state = state.get("last_sensor_state") if has_container else None
    ml_outputs   = state.get("ml_outputs")        if has_container else None

    answer = reasoning_generate(
        question=question,
        context=context,
        history=history,
        sensor_state=sensor_state,
        ml_outputs=ml_outputs,
    )

    return {"response": answer}


def request_clarification(state: AgentState) -> dict[str, Any]:
    """Triggered when intent confidence < 0.7.

    Asks one targeted clarifying question based on keywords in the message.
    Falls back to a generic rephrase prompt when no keyword hint matches.
    """
    intent = state.get("intent", "UNKNOWN")
    confidence = state.get("confidence", 0.0)
    print(f"[node] request_clarification  (intent={intent}, confidence={confidence:.2f})")

    message = _last_user_message(state).lower()

    # Find the most relevant clarifying question
    clarifying_q = (
        "Could you be a bit more specific? Are you asking a **general knowledge question**, "
        "trying to **adjust a container parameter**, checking **system/sensor status**, "
        "or **troubleshooting a problem** with your culture?"
    )
    for keywords, question in _CLARIFY_HINTS:
        if any(kw in message for kw in keywords):
            clarifying_q = question
            break

    response = clarifying_q
    return {
        "response": response,
        "chat_history": [{"role": "assistant", "content": response}],
    }


def reject_off_domain(state: AgentState) -> dict[str, Any]:
    """Triggered when the question is unrelated to spirulina cultivation.

    Acknowledges politely and redirects to the supported domain.
    """
    print("[node] reject_off_domain")
    response = (
        "That topic is outside what I can help with — I'm specialized in "
        "**Spirulina platensis cultivation**: pH and nutrient management, "
        "contamination diagnosis, harvest timing, growth monitoring, and culture troubleshooting.\n\n"
        "Is there anything spirulina-related I can help you with?"
    )
    return {
        "response": response,
        "chat_history": [{"role": "assistant", "content": response}],
    }


def recall_memory(state: AgentState) -> dict[str, Any]:
    """Triggered when the user asks about their previous conversation.

    Returns a formatted summary of the stored chat history,
    excluding the current triggering message.
    """
    print("[node] recall_memory")
    history = state.get("chat_history", [])

    # Exclude the current user message (last entry that triggered this node)
    past = history[:-1] if history and history[-1].get("role") == "user" else history

    if not past:
        response = (
            "We haven't discussed anything yet! "
            "Feel free to ask me anything about spirulina cultivation."
        )
    else:
        lines = []
        for msg in past:
            role = "**You**" if msg["role"] == "user" else "**SpirulinaAI**"
            content = msg["content"]
            if len(content) > 300:
                content = content[:297] + "..."
            lines.append(f"{role}: {content}")
        body = "\n\n".join(lines)
        response = f"## Our Conversation So Far\n\n{body}"

    return {
        "response": response,
        "chat_history": [{"role": "assistant", "content": response}],
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
