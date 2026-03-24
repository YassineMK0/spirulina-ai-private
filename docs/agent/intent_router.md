# agent/intent_router.py

## Purpose
Classifies the user's latest message into one of four pipeline intents using an LLM. Returns JSON `{intent, confidence}` which the graph uses to route the request.

## Six intents

| Intent | Meaning | Graph target |
|--------|---------|-------------|
| `KNOWLEDGE` | Factual / how-to question about spirulina | `retrieve_rag` |
| `UPDATE` | Change / set a container parameter | `retrieve_rag` |
| `HARVEST` | Harvest timing / readiness | `retrieve_rag` |
| `SYSTEM` | Device status, alerts, sensors | `retrieve_rag` |
| `OFF_DOMAIN` | **Clearly** unrelated (e.g. "who won the World Cup?"). Greetings, platform questions, and anything that could relate to cultivation default to `KNOWLEDGE`. | `reject_off_domain` → END |
| `MEMORY_RECALL` | User asking to recall past conversation | `recall_memory` → END |

`UNKNOWN` is a fallback label (parse failure) — treated as low-confidence.

## Confidence threshold
`CONFIDENCE_THRESHOLD = 0.7`
If confidence < 0.7 → graph routes to `request_clarification` regardless of intent.
`OFF_DOMAIN` and `MEMORY_RECALL` are only followed when confidence ≥ 0.7.

## LLM providers (configurable via env vars)
| Env var | Value | Model used |
|---------|-------|-----------|
| `INTENT_MODEL_PROVIDER` | `groq` (default) | `llama-3.1-8b-instant` |
| `INTENT_MODEL_PROVIDER` | `openai` | `gpt-4o-mini` |
| `INTENT_MODEL_PROVIDER` | `ollama` | `mistral` (local) |

Model name overridable via `INTENT_MODEL_NAME`.

## How it works
1. Extracts the last user message from `state["chat_history"]`
2. Sends it to the LLM with a strict classification prompt
3. LLM returns JSON: `{"intent": "KNOWLEDGE", "confidence": 0.95}`
4. `_parse_response()` handles LLM quirks (markdown fences, trailing text, invalid JSON)
5. Falls back to `UNKNOWN / 0.0` on any parse failure

## Chain initialization
`_chain` is a module-level singleton built lazily via `_get_chain()`. It is: `INTENT_PROMPT | LLM | StrOutputParser`

## Prompt design
- System prompt instructs the LLM to return ONLY valid JSON
- `{{ }}` used to escape braces in the prompt template (LangChain template requirement)
- Max tokens: 40 (intent + confidence is a tiny output)
- Temperature: 0 (deterministic)

## Test results
30-message test suite in `tests/test_intent_router.py` — 90% accuracy on `llama-3.1-8b-instant`.

## Dependencies
- `langchain_core` — `ChatPromptTemplate`, `StrOutputParser`
- `langchain_groq` / `langchain_openai` / `langchain_community` (conditionally)
- `agent.state` — `AgentState`
