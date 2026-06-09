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


_AGENTIC_SYSTEM = """\
You are SpirulinaAI — a spirulina cultivation expert agent.
Your job is to ACT, not just inform. When given a problem:

STEP 1 — PLAN (always do this first, in the response before calling any tool)
Write a short markdown plan:
```
## Plan
1. <what you will check>
2. <what you will calculate>
3. <what you will recommend>
```

STEP 2 — ACT
Call the relevant tools to gather exact figures. Available tools:
- `get_recent_alerts`         — ALWAYS call this first when the user asks about alerts, warnings, or what happened on the container. Read the REAL alert log — never guess.
- `calculate_ph_correction`   — dose of NaHCO3/acid to hit target pH
- `calculate_ec_correction`   — nutrient addition or dilution to hit target EC
- `diagnose_culture_symptom`  — structured checklist for visible symptoms
- `format_action_plan`        — format final prioritised checklist

CRITICAL RULES FOR ALERTS:
- If the user mentions "alert", "warning", "alarm", "what happened", or asks if anything is wrong → call `get_recent_alerts` IMMEDIATELY before anything else
- Base your alert answer on what `get_recent_alerts` returns — NOT on live sensor thresholds
- If `get_recent_alerts` returns no alerts, say so clearly — do NOT invent alerts from sensor readings
- Never contradict the alert log in your synthesis section

STEP 3 — SYNTHESISE
After all tool calls complete, write the final response:

## Situation
[1–2 sentences — what is happening and why it matters]

## Analysis
[What the sensor data, ML outputs, and tool results reveal]

## Action Steps
[Reference the tool output checklists here — do not invent doses]

## Follow-up
[What to monitor and when to re-check]

RULES
- Use tools when you need calculations — never guess chemical doses
- Keep Action Steps to 3–5 items max
- Bold critical values and actions
- If anomaly score > 0.8 or status=error, say so clearly and recommend specialist contact
- Respond in the same language the user asked in (FR or EN)
"""

# Max tool-call iterations before forcing final answer
_MAX_ITERATIONS = 4


def reasoning_agent(state: AgentState) -> dict[str, Any]:
    """Agentic stage — ReAct loop for HARVEST, SYSTEM, and UPDATE intents.

    Pipeline:
    1. PLAN   — LLM outputs a markdown plan (visible to user)
    2. ACT    — LLM calls domain tools (pH calc, EC calc, diagnosis …)
    3. SYNTH  — LLM synthesises a rich markdown response with actionable steps

    Falls back to single-shot generation on any LLM or tool error.
    """
    print("[node] reasoning_agent  (agentic ReAct)")

    import os, re, json
    from functools import lru_cache
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    from agent.tools import get_agent_tools

    # ── Build context block ─────────────────────────────────────────────────
    question      = _last_user_message(state)
    context       = state.get("rag_context", "")
    history       = state.get("chat_history", [])
    has_container = state.get("has_container", False)
    sensor_state  = state.get("last_sensor_state") or {} if has_container else {}
    ml_outputs    = state.get("ml_outputs")         or {} if has_container else {}

    context_parts: list[str] = []
    if context:
        context_parts.append(f"<knowledge_base>\n{context}\n</knowledge_base>")
    if sensor_state:
        lines = "\n".join(f"  {k}: {v}" for k, v in sensor_state.items())
        context_parts.append(f"<sensor_readings>\n{lines}\n</sensor_readings>")
    if ml_outputs:
        context_parts.append(f"<ml_outputs>\n{json.dumps(ml_outputs, indent=2)}\n</ml_outputs>")

    recent_hist = history[-8:] if len(history) > 8 else history
    hist_lines = [
        f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}"
        for m in recent_hist[:-1]  # exclude current user message
        if m.get("content")
    ]

    human_content = ""
    if context_parts:
        human_content += "\n\n".join(context_parts) + "\n\n"
    if hist_lines:
        human_content += "<conversation_history>\n" + "\n".join(hist_lines) + "\n</conversation_history>\n\n"
    human_content += f"Question: {question}"

    # ── Initialise tool-bound LLM ───────────────────────────────────────────
    tools = get_agent_tools()
    tools_by_name = {t.name: t for t in tools}

    provider = os.getenv("GENERATOR_MODEL_PROVIDER", "groq").lower()
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model=os.getenv("GENERATOR_MODEL_NAME", "llama-3.3-70b-versatile"),
                temperature=0.1,
                max_tokens=2048,
            ).bind_tools(tools)
        else:
            from langchain_openai import ChatOpenAI
            kwargs = {
                "model": os.getenv("REASONING_MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b:free"),
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            if provider == "openrouter":
                kwargs["api_key"] = os.getenv("OPENROUTER_API_KEY", "")
                kwargs["base_url"] = "https://openrouter.ai/api/v1"
            llm = ChatOpenAI(**kwargs).bind_tools(tools)
    except Exception as exc:
        print(f"  [agent] LLM init failed: {exc} — falling back to single-shot")
        from rag.generator.generate import reasoning_generate
        answer = reasoning_generate(
            question=question, context=context, history=history,
            sensor_state=sensor_state or None, ml_outputs=ml_outputs or None,
        )
        return {"response": answer, "plan": "", "tool_calls": []}

    # ── ReAct loop ──────────────────────────────────────────────────────────
    messages: list = [
        SystemMessage(content=_AGENTIC_SYSTEM),
        HumanMessage(content=human_content),
    ]
    tool_calls_log: list[dict] = []
    plan_text = ""

    for iteration in range(_MAX_ITERATIONS):
        print(f"  [agent] iteration {iteration + 1}/{_MAX_ITERATIONS}")
        try:
            response = llm.invoke(messages)
        except Exception as exc:
            print(f"  [agent] LLM error on iteration {iteration + 1}: {exc}")
            break

        messages.append(response)

        # Capture the plan from the first AI message that has text
        if not plan_text and isinstance(response, AIMessage) and response.content:
            plan_text = response.content

        # No tool calls → agent is done
        if not getattr(response, "tool_calls", None):
            print(f"  [agent] finished after {iteration + 1} iterations")
            break

        # Execute each tool call
        for tc in response.tool_calls:
            name    = tc.get("name", "")
            args    = tc.get("args", {})
            call_id = tc.get("id", f"call_{name}")

            print(f"  [agent] tool: {name}({list(args.keys())})")
            fn = tools_by_name.get(name)
            if fn is None:
                result_text = f"Error: unknown tool '{name}'"
            else:
                try:
                    result_text = fn.invoke(args)
                except Exception as exc:
                    result_text = f"Tool error ({name}): {exc}"

            tool_calls_log.append({"tool": name, "args": args, "result": str(result_text)[:600]})
            messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))

    # ── Extract final answer ────────────────────────────────────────────────
    # Walk messages in reverse to find the last AI text (not a tool-call stub)
    final_text = ""
    for msg in reversed(messages):
        if (
            isinstance(msg, AIMessage)
            and msg.content
            and not getattr(msg, "tool_calls", None)
        ):
            final_text = msg.content
            break

    if not final_text:
        # Last message has text but also has tool_calls (planning message) — use it
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_text = msg.content
                break

    if not final_text:
        final_text = "I was unable to generate a response. Please try again."

    # Strip chain-of-thought tags (R1-style models)
    final_text = re.sub(r"<think>.*?</think>", "", final_text, flags=re.DOTALL).strip()

    print(f"  [agent] tool_calls={len(tool_calls_log)}  response_len={len(final_text)}")

    existing_tools = state.get("tools_used") or []
    agentic_tool_labels = [f"tool:{tc['tool']}" for tc in tool_calls_log]

    return {
        "response":   final_text,
        "plan":       plan_text,
        "tool_calls": tool_calls_log,
        "tools_used": existing_tools + agentic_tool_labels,
    }


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
