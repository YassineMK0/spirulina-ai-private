"""Agent state schema shared across all graph nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # ── identity / session ────────────────────────────────
    user_id: str
    container_id: str
    has_container: bool

    # ── intent classification ─────────────────────────────
    intent: str
    confidence: float

    # ── RAG ───────────────────────────────────────────────
    rag_context: str

    # ── ML model outputs ──────────────────────────────────
    ml_outputs: dict[str, Any]

    # ── conversation ──────────────────────────────────────
    chat_history: Annotated[list[dict], operator.add]

    # ── hardware / IoT ────────────────────────────────────
    last_sensor_state: dict[str, Any]

    # ── final answer ──────────────────────────────────────
    response: str
