"""Agent state schema shared across all graph nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # identity / session
    user_id: str
    container_id: str
    has_container: bool
    tier: str           # "free" | "pro"

    # intent classification
    intent: str
    confidence: float

    # RAG
    rag_context: str

    # sensor + ML
    last_sensor_state: dict   # latest MQTT reading
    ml_outputs: dict          # merged M1/M2/M3 results
    tools_used: list[str]     # tool names shown in the UI pill row

    # structured response for frontend rendering
    content: dict             # {type: "text"|"diagnosis"|"harvest"|"phases", ...}

    # conversation
    chat_history: Annotated[list[dict], operator.add]

    # agentic fields
    plan: str                  # markdown plan generated before tool execution
    tool_calls: list[dict]     # log of {tool, args, result} for each tool call

    # final answer (markdown — kept for LLM chain compatibility)
    response: str
