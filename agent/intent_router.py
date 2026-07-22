"""Intent Router -- classifies the latest user message into a pipeline intent.

Runs after check_container has confirmed container_id in state.
Returns { intent, confidence }. If confidence < 0.7 the graph routes
to a clarification node instead of continuing the main pipeline.



Intents
-------
KNOWLEDGE     - factual / how-to question        -> RAG pipeline
UPDATE        - change container parameters       -> write path
HARVEST       - harvest timing / readiness        -> ML models
SYSTEM        - device status, alerts, errors     -> sensor / diagnostics path
OFF_DOMAIN    - unrelated to spirulina            -> polite redirect
MEMORY_RECALL - asking about past conversation   -> memory recall node
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agent.state import AgentState

# -- valid intents ---------------------------------------------------------
VALID_INTENTS = {"KNOWLEDGE", "UPDATE", "HARVEST", "SYSTEM", "OFF_DOMAIN", "MEMORY_RECALL", "UNKNOWN"}

CONFIDENCE_THRESHOLD = 0.7

# -- prompt ----------------------------------------------------------------
INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a spirulina smart-farming assistant.

Given the user's latest message, respond with a JSON object containing
exactly two keys: "intent" and "confidence".

Intent labels (pick ONE):
  KNOWLEDGE     - the user asks a factual, how-to, or general-knowledge question
                  about spirulina cultivation (pH, nutrients, light, temperature, etc.).
  UPDATE        - the user wants to change, set, or adjust a container parameter
                  (e.g. "set pH to 9.5", "turn on the light", "change temperature").
  HARVEST       - the user asks about harvest timing, readiness, biomass density,
                  or wants to trigger / schedule a harvest.
  SYSTEM        - the user asks about device status, sensor readings, connectivity,
                  error logs, alerts, or system health (e.g. "is the pump running?",
                  "show me sensor errors", "what's the system status?").
  OFF_DOMAIN    - the question is CLEARLY and OBVIOUSLY unrelated to spirulina,
                  algae, aquaculture, farming, biology, or this platform.
                  Examples: "who won the World Cup?", "write me a poem", "what is 2+2".
                  DO NOT use OFF_DOMAIN for:
                    - greetings or small talk ("hello", "hi", "thanks") -> use KNOWLEDGE
                    - questions about this app / platform / system -> use KNOWLEDGE or SYSTEM
                    - questions about algae, microalgae, or any related biology -> use KNOWLEDGE
                    - anything that could plausibly relate to cultivation -> use KNOWLEDGE
                  When in doubt, prefer KNOWLEDGE over OFF_DOMAIN.
  MEMORY_RECALL - the user is asking to recall a previous message, past topic, or
                  their conversation history (e.g. "what did we discuss?",
                  "what was my last question?", "remind me what you said about pH",
                  "show me our conversation", "what did I ask before?").

Confidence is a float between 0.0 and 1.0 reflecting how certain you are.

Reply with ONLY valid JSON, no markdown, no explanation.
Example: {{"intent": "KNOWLEDGE", "confidence": 0.95}}"""

INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", INTENT_SYSTEM_PROMPT),
        ("human", "{message}"),
    ]
)


def _get_llm():
    """Return the intent classifier LLM (Groq / OpenAI / Ollama, from env)."""
    provider = os.getenv("INTENT_MODEL_PROVIDER", "groq").lower()

    # -- Groq (default) ----------------------------------------------------
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=os.getenv("INTENT_MODEL_NAME", "llama-3.1-8b-instant"),
            temperature=0,
            max_tokens=40,
        )

    # -- OpenAI ------------------------------------------------------------
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("INTENT_MODEL_NAME", "gpt-4o-mini"),
            temperature=0,
            max_tokens=40,
        )

    # -- local / Ollama ------------------------------------------------------
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("INTENT_MODEL_NAME", "qwen3:8b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,
            num_predict=200,
            reasoning=False,  # qwen3 thinking mode would burn the whole
                               # token budget on <think> before ever
                               # emitting the JSON this classifier needs
        )

    raise ValueError(f"Unsupported INTENT_MODEL_PROVIDER: {provider}")


def _extract_last_user_message(state: AgentState) -> str:
    """Pull the most recent user message from chat_history."""
    for msg in reversed(state.get("chat_history", [])):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _parse_response(raw: str) -> tuple[str, float]:
    """Parse LLM JSON output into (intent, confidence).

    Handles common LLM quirks: markdown fences, trailing text, etc.
    Falls back to UNKNOWN / 0.0 on any parse failure.
    """
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the raw string
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                return ("UNKNOWN", 0.0)
        else:
            return ("UNKNOWN", 0.0)

    intent = str(data.get("intent", "UNKNOWN")).upper().strip()
    if intent not in VALID_INTENTS:
        intent = "UNKNOWN"

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    return (intent, confidence)


# -- chain (lazy-initialised once, reset when prompt changes) --------------
_chain = None


def _get_chain():
    global _chain
    if _chain is None:
        _chain = INTENT_PROMPT | _get_llm() | StrOutputParser()
    return _chain


def reset_chain():
    """Force rebuild of the chain (call after updating INTENT_SYSTEM_PROMPT at runtime)."""
    global _chain
    _chain = None


# -- public node function --------------------------------------------------
def classify_intent(state: AgentState) -> dict[str, Any]:
    """LangGraph node -- classify the user message into an intent.

    Returns { intent, confidence } merged into state.
    Expects check_container to have already run.
    """
    message = _extract_last_user_message(state)

    if not message:
        print("[intent_router] no user message found -> UNKNOWN 0.0")
        return {"intent": "UNKNOWN", "confidence": 0.0}

    raw = _get_chain().invoke({"message": message})
    intent, confidence = _parse_response(raw)
    print(
        f"[intent_router] '{message[:60]}' "
        f"-> {intent} ({confidence:.2f})  raw={raw!r}"
    )
    return {"intent": intent, "confidence": confidence}
