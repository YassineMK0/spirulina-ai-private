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
    """Stage 4 — run M1/M2/M3 on the latest sensor data.

    Data sources (in priority order):
      1. last_sensor_state  — live MQTT reading (populated by read_sensors)
      2. DB latest row      — last persisted reading (covers server restarts)

    If neither source has data, returns empty outputs immediately.
    """
    print("[node] run_ml_models")
    container_id = state.get("container_id") or ""
    if not container_id:
        return {"ml_outputs": {}, "tools_used": []}

    import pandas as pd
    from agent.sensors import get_history
    from data.store import sensor_store

    # ── Resolve latest reading ────────────────────────────────────────────────
    reading = state.get("last_sensor_state") or {}
    if not reading:
        rows = sensor_store.get_latest(container_id, n=1)
        if rows:
            reading = rows[-1]
            print(f"  [ml] MQTT cache empty — using latest DB row ({reading.get('date','?')})")

    if not reading:
        print("  [ml] no sensor data available — skipping ML")
        return {"ml_outputs": {}, "tools_used": []}

    ml: dict[str, Any] = {}
    tools: list[str]   = ["sensor.read()"]

    # ── M1: LSTM anomaly detection ────────────────────────────────────────────
    try:
        from api.predict_lstm import predict_df, load_artifact

        history = get_history(container_id)
        if history:
            artifact = load_artifact()
            result   = predict_df(pd.DataFrame(history), artifact)
            last     = result.iloc[-1]
            score    = float(last["anomaly_score"]) if not pd.isna(last["anomaly_score"]) else 0.0
            anomaly  = bool(last["is_anomaly"])
            severity = str(last["severity"])
            trend    = str(last["trend_direction"])

            ml.update({
                "anomaly":        anomaly,
                "anomaly_flag":   anomaly,
                "score":          round(score, 4),
                "severity":       severity,
                "trend":          trend,
                "anomaly_detail": (
                    f"Severity: **{severity}**  |  Score: {score:.3f}  |  Trend: {trend}"
                    if anomaly else f"Score: {score:.3f} (normal)"
                ),
            })
            tools.append("M1 Anomaly Detector")
            print(f"  [m1] anomaly={anomaly}  severity={severity}  score={score:.3f}")
    except Exception as exc:
        print(f"  [warn] M1 failed: {exc}")

    # ── M2: next-day turbidity forecast ──────────────────────────────────────
    try:
        from api.predict_lgbm import predict, load_artifact as load_m2

        history = get_history(container_id)
        if len(history) >= 5:
            forecast = predict(pd.DataFrame(history), load_m2())
            ml["turbidity_forecast"] = forecast
            tools.append("M2 Growth Predictor")
            print(f"  [m2] p50={forecast.get('prediction')}")
    except Exception as exc:
        print(f"  [warn] M2 failed: {exc}")

    # ── M3: harvest readiness scheduler ──────────────────────────────────────
    try:
        from api.predict_lgbm_harvest import schedule, load_artifacts as load_m3

        history   = get_history(container_id)
        n_readings = len(history)
        min_rows  = 6

        if n_readings >= min_rows:
            m3_art, m2_art = load_m3()
            harvest = schedule(pd.DataFrame(history), m3_art, m2_art)
            ml["harvest"] = harvest
            tools.append("M3 Harvest Planner")
            print(f"  [m3] recommendation={harvest.get('recommendation')}")
        else:
            # Not enough history — tell the reasoning agent explicitly
            ml["harvest"] = {
                "cold_start":     True,
                "readings_have":  n_readings,
                "readings_need":  min_rows,
                "recommendation": f"Not enough data yet ({n_readings}/{min_rows} readings). "
                                  f"Need {min_rows - n_readings} more sensor readings before M3 can predict harvest timing.",
            }
            print(f"  [m3] cold start — only {n_readings}/{min_rows} readings")
    except Exception as exc:
        print(f"  [warn] M3 failed: {exc}")

    return {"ml_outputs": ml, "tools_used": tools}


def read_sensors(state: AgentState) -> dict[str, Any]:
    """Stage 3b — fetch latest reading from the MQTT cache."""
    print("[node] read_sensors")
    container_id = state.get("container_id") or ""
    if not container_id:
        return {"last_sensor_state": {}}
    try:
        from agent.sensors import get_sensor_reading
        reading = get_sensor_reading(container_id)
        status  = reading.get("status", "no data") if reading else "no data"
        print(f"  [sensors] container={container_id}  status={status}")
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


def _build_content(state: AgentState) -> dict:
    """Build the structured content object consumed by the Next.js frontend.

    Maps intent + ml_outputs to one of four content types:
      diagnosis — M1 anomaly detected (sensors + recommended action)
      harvest   — HARVEST intent (M3 3-day schedule + M2 forecast)
      text      — everything else (plain conversational response)
    """
    intent  = state.get("intent", "KNOWLEDGE").upper()
    ml      = state.get("ml_outputs") or {}
    raw     = state.get("response", "")
    sensors = state.get("last_sensor_state") or {}

    # --- DIAGNOSIS: anomaly flag from M1 ---
    if ml.get("anomaly_flag"):
        sensor_cards = []
        thresholds = {
            "pH":          {"unit": "",      "opt": "9.5–10.5", "min_ok": 9.5, "max_ok": 10.5},
            "temperature": {"unit": " °C",   "opt": "30–37°C",  "min_ok": 30,  "max_ok": 37},
            "turbidity":   {"unit": " NTU",  "opt": "50–250",   "min_ok": 50,  "max_ok": 250},
            "EC":          {"unit": " µS/cm","opt": "1500–3000","min_ok": 1500,"max_ok": 3000},
            "DO":          {"unit": " mg/L", "opt": "6–8",      "min_ok": 6,   "max_ok": 8},
        }
        for key, meta in thresholds.items():
            val = sensors.get(key)
            if val is None:
                continue
            fval     = float(val)
            is_alert = not (meta["min_ok"] <= fval <= meta["max_ok"])
            sensor_cards.append({
                "label":   key,
                "val":     str(round(fval, 2)),
                "unit":    meta["unit"],
                "opt":     meta["opt"],
                "isAlert": is_alert,
            })
        return {
            "type":    "diagnosis",
            "cause":   raw,
            "sensors": sensor_cards,
            "action":  {"dose": "", "note": raw},
            "score":   ml.get("score", 0),
            "severity":ml.get("severity", "low"),
            "trend":   ml.get("trend", "stable"),
        }

    # --- HARVEST: M3 schedule available ---
    if intent == "HARVEST" and ml.get("harvest"):
        h      = ml["harvest"]
        today  = h.get("today",     {})
        tmrw   = h.get("tomorrow",  {})
        d2     = h.get("day_after", {})
        rec    = h.get("recommendation", "")
        tf     = ml.get("turbidity_forecast") or {}
        return {
            "type":      "harvest",
            "body":      raw,
            "schedule":  {
                "today":     today,
                "tomorrow":  tmrw,
                "day_after": d2,
            },
            "recommendation": rec,
            "turbidity_forecast": tf,
        }

    # --- DEFAULT: plain text ---
    return {"type": "text", "text": raw}


def format_response(state: AgentState) -> dict[str, Any]:
    """Stage 7 — build structured content + update chat history."""
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

    content = _build_content(state)

    return {
        "response":    formatted,
        "content":     content,
        "chat_history": [{"role": "assistant", "content": formatted}],
    }
