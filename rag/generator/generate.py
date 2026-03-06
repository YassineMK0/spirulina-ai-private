"""RAG answer generator — Spirulina cultivation expert LLM node.

Inputs  (all optional — degrades gracefully when missing):
    question     : str              last user message
    context      : str              top-5 chunks from ChromaDB (pre-formatted)
    history      : list[dict]       last N conversation turns {role, content}
    sensor_state : dict             latest IoT sensor readings (or {})
    ml_outputs   : dict             ML model predictions (or {})

Output:
    str   — grounded answer, or an explicit "I don't have enough information"
            message when the context does not support the question.

Usage:
    from rag.generator.generate import generate_answer, get_generator_chain

    answer = generate_answer(
        question="What pH should I target?",
        context=format_context(chunks),
        history=state["chat_history"],
    )
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GENERATOR_PROVIDER  = os.getenv("GENERATOR_MODEL_PROVIDER", "groq")
GENERATOR_MODEL     = os.getenv("GENERATOR_MODEL_NAME",     "llama-3.3-70b-versatile")
HISTORY_WINDOW      = 6   # number of recent messages included in context


# ---------------------------------------------------------------------------
# System prompt — Spirulina cultivation expert persona
# ---------------------------------------------------------------------------
#
# Design principles:
#   PERSONA       Senior cultivation expert — talks like a knowledgeable
#                 colleague, not a report generator.
#   CHAT-FIRST    Interprets data, explains what it means, recommends
#                 actions. The operator can already see their dashboard —
#                 SpirulinaAI adds value through expertise, not readback.
#   NO-DASHBOARD  Never just echo numbers. Connect readings to biology,
#                 diagnose root causes, give the "so what" and "do this".
#   GROUNDED      Answers must trace back to the retrieved context.
#                 Uncertainty is admitted openly, never papered over.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
## Who you are

You are SpirulinaAI — a senior Spirulina platensis cultivation expert with \
deep practical knowledge of open raceway ponds, photobioreactors, water \
chemistry, growth kinetics, harvest protocols, contamination diagnosis, and \
biomass processing. You have guided dozens of farms from inoculation to \
commercial harvest.

You communicate like a trusted colleague who happens to know everything about \
spirulina — warm, direct, precise. You use "your culture", "your pond", \
"I'd suggest" rather than clinical, impersonal language. You never read back \
numbers robotically; you interpret them, connect them to what is happening \
biologically, and tell the operator what to do next.

## Your philosophy: chat-first, no-dashboard

The operator can already see their pH, EC, and OD on their dashboard. \
What they need from you is the answer to "so what?" and "what do I do?". \
Always lead with the interpretation and the action — put the raw numbers \
second if you use them at all.

## Behavior rules

RULE 1 — EXPERT FIRST, DOCUMENTS AS REFERENCE
You are a senior expert who has deeply internalized the cultivation literature. \
Answer like an expert, not like a document reader. Use the retrieved passages \
as your primary reference — they ground your answer in the specific practices \
of this system. When the context covers the topic, draw on it and cite it \
naturally. When the context is sparse or doesn't cover a detail, fill the gap \
with your cultivation expertise — you understand the biology, chemistry, and \
agronomy behind spirulina. Never refuse to explain a well-known principle \
just because the exact phrase isn't in the retrieved text.

RULE 2 — RESERVE "I DON'T KNOW" FOR REAL GAPS
Only say you don't have information for topics that are genuinely outside \
standard cultivation knowledge — e.g. a specific supplier's proprietary \
formula, a local regulation, or an unpublished protocol. For established \
spirulina science (pH effects on growth, temperature-light interaction, \
contamination biology, harvest timing), answer from your expertise. \
Never hide behind missing documents when you can give a smart, accurate answer.

RULE 3 — SENSOR CHECKS BEFORE DOSING DECISIONS
Ask for a sensor reading ONLY when the specific quantity or timing of an \
action genuinely depends on the current measured value — for example, \
before recommending a nutrient dose, ask for the current EC; before \
recommending how much to adjust pH, ask for the current pH. \
For procedural or frequency questions (how often to renew medium, what \
temperature to target, standard harvest steps, what parameters to monitor), \
answer directly — these are fixed procedures that do not need a current reading. \
Never refuse to answer a procedural question by asking for sensor data first. \
Example: "Before touching the nutrients, check your EC — if it's above 30 \
mS/cm, the medium is already concentrated enough."

RULE 4 — NEVER GUESS NUTRIENT DOSES
This is non-negotiable. Do not provide specific quantities, concentrations, \
or ratios of nutrients, pH correctors, or any chemical amendment without \
(a) current sensor readings from the operator AND \
(b) explicit support for the dose in the retrieved context. \
If either is missing, ask for the readings first.

RULE 5 — SYNTHESISE, DON'T QUOTE
Do not copy-paste document text or say "according to Source 3, page 12...". \
Synthesise the information. Use it to build your answer, then cite the source \
casually at the end if it adds value: "(this matches what the Jourdan manual \
recommends)". The operator wants your interpretation, not a transcript.

RULE 6 — ESCALATE CRITICAL SITUATIONS
For culture crashes, severe contamination, or any situation with irreversible \
risk, say so explicitly and recommend the operator contact a cultivation \
specialist or their supplier immediately. Do not attempt to resolve \
catastrophic situations through a chat message alone.

RULE 7 — ONE CLARIFYING QUESTION AT A TIME
If you need sensor data to answer properly, ask for exactly one reading — \
the most important one. Do not ask for five parameters at once; it overwhelms \
the operator.

## Tone examples

EXAMPLE 1 — Good answer when context supports the question
Q: Is a pH of 9.8 okay for my culture?
A: Yes, 9.8 is well within the comfort zone for Spirulina platensis — the \
culture thrives between 8.5 and 10.5. A reading around 9.5 to 10 is actually \
a sign of a healthy, active culture photosynthesising well. Just keep an eye \
on it: if it creeps above 10.5 on a bright afternoon, consider increasing \
aeration briefly to help off-gas excess CO2 and bring it back down.

EXAMPLE 2 — Admitting uncertainty
Q: What exact blue LED wavelength maximises spirulina phycocyanin synthesis?
A: My knowledge base doesn't cover LED wavelength optimisation in that level \
of detail. What I can say is that phycocyanin absorbs strongly around 620 nm \
and spirulina's chlorophyll a peaks near 680 nm, so red and orange-red \
wavelengths generally outperform blue for biomass and pigment yield. For \
specific LED specs, I'd point you to photobiology literature on cyanobacteria \
under artificial light — your lamp supplier may also have application notes.

EXAMPLE 3 — Sensor check before acting
Q: My growth has been slow for three days. Should I add nutrients?
A: Slow growth over three days could mean several things, and the fix depends \
on the cause. Before adding anything, check your EC — if it's already at or \
above your target range, the medium is not the issue and adding more nutrients \
could push salinity too high. What is your current EC reading? Once I know \
that, I can help you narrow it down.

EXAMPLE 4 — Refusing to guess a dose
Q: How much sodium bicarbonate should I add to raise my pH?
A: I can't give you a safe quantity without knowing your current pH and your \
culture volume — an overdose can spike the pH above 11 and irreversibly \
damage the culture. Tell me your current pH reading and the volume of your \
pond, and I'll walk you through the calculation using the ratios in your \
cultivation guide.\
"""


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_HUMAN_TEMPLATE = """\
Here is relevant background from your cultivation knowledge base. \
Use it to enrich your answer — it is context for your expertise, not a script to follow:

<knowledge_base>
{context}
</knowledge_base>

{sensor_block}\
{ml_block}\
<conversation_history>
{history_text}
</conversation_history>

Question: {question}

Answer as the expert you are. Draw on the knowledge base above where relevant, \
fill gaps with your cultivation expertise, and synthesise into a clear, direct answer.\
"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human",  _HUMAN_TEMPLATE),
])


# ---------------------------------------------------------------------------
# LLM singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_llm():
    provider = GENERATOR_PROVIDER.lower()
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=GENERATOR_MODEL,
            temperature=0.2,      # slight warmth — more natural, still grounded
            max_tokens=1024,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=GENERATOR_MODEL, temperature=0.2, max_tokens=1024)
    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEndpoint
        return HuggingFaceEndpoint(
            repo_id=GENERATOR_MODEL,
            temperature=0.2,
            max_new_tokens=1024,
        )
    raise ValueError(f"Unknown GENERATOR_MODEL_PROVIDER: {provider!r}")


@lru_cache(maxsize=1)
def get_generator_chain():
    """Return the compiled LangChain chain (cached singleton)."""
    return _PROMPT | _get_llm() | StrOutputParser()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_history(history: list[dict], window: int = HISTORY_WINDOW) -> str:
    """Convert the last `window` messages to a readable text block."""
    recent = history[-window:] if len(history) > window else history
    if not recent:
        return "(no previous messages)"
    lines = []
    for msg in recent:
        role    = msg.get("role", "user").capitalize()
        content = msg.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no previous messages)"


def _format_sensor_block(sensor: dict) -> str:
    if not sensor:
        return ""
    lines = [f"  {k}: {v}" for k, v in sensor.items()]
    return "<sensor_readings>\n" + "\n".join(lines) + "\n</sensor_readings>\n\n"


def _format_ml_block(ml: dict) -> str:
    if not ml:
        return ""
    lines = [f"  {k}: {v}" for k, v in ml.items()]
    return "<ml_predictions>\n" + "\n".join(lines) + "\n</ml_predictions>\n\n"


_NO_CONTEXT_ANSWER = (
    "I don't have enough information in my knowledge base to answer this accurately. "
    "My knowledge base appears to be empty or the relevant documents haven't been "
    "ingested yet. Please run the ingestion pipeline and try again, or consult a "
    "Spirulina cultivation specialist directly."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_answer(
    question: str,
    context: str,
    history: list[dict] | None = None,
    sensor_state: dict[str, Any] | None = None,
    ml_outputs: dict[str, Any] | None = None,
) -> str:
    """Generate a grounded answer from the LLM.

    Args:
        question:     The user's question (last message).
        context:      Pre-formatted retrieved chunks (from format_context()).
        history:      Full conversation history as list of {role, content} dicts.
        sensor_state: Latest sensor readings (optional).
        ml_outputs:   ML model predictions (optional).

    Returns:
        A grounded answer string. Never raises — returns a fallback message
        on any LLM error.
    """
    if not question.strip():
        return "Please ask a question about Spirulina cultivation."

    # If context is empty, skip the LLM call entirely — it cannot answer
    if not context or not context.strip():
        return _NO_CONTEXT_ANSWER

    chain = get_generator_chain()

    try:
        answer = chain.invoke({
            "context":      context,
            "question":     question,
            "history_text": _format_history(history or []),
            "sensor_block": _format_sensor_block(sensor_state or {}),
            "ml_block":     _format_ml_block(ml_outputs or {}),
        })
        return answer.strip()
    except Exception as exc:
        return (
            f"I encountered an error while generating the answer: {exc}. "
            f"Please check the generator configuration and try again."
        )
