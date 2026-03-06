# rag/generator/ — RAG Answer Generator

LLM node that synthesizes a grounded answer from retrieved chunks,
conversation history, and (optionally) live sensor and ML data.

---

## File

### `generate.py`

#### Persona & grounding rules

The system prompt establishes **SpirulinaAI** — a senior expert in
Spirulina platensis cultivation — with strict grounding rules:

1. Answer ONLY from the `<context>` block (retrieved chunks).
2. If context is empty → skip the LLM call entirely and return an
   explicit "I don't have enough information" message.
3. If context partially covers the question → answer what is supported
   and flag the gap clearly.
4. Never invent facts, dosages, or recommendations not in the context.
5. Cite source filenames when visible.
6. Incorporate sensor readings and ML predictions when provided.

#### Prompt structure

```
[system]  SpirulinaAI persona + grounding rules

[human]   <context>       top-5 retrieved chunks
          <sensor_readings>  live IoT data (container users only)
          <ml_predictions>   model outputs (container users only)
          <conversation_history>  last 6 messages
          <question>      current user message
```

#### LLM

Default: **Groq `llama-3.3-70b-versatile`**
(`temperature=0.2`, `max_tokens=1024`)

Configurable via env vars:
```
GENERATOR_MODEL_PROVIDER=groq        # groq | openai | huggingface
GENERATOR_MODEL_NAME=llama-3.3-70b-versatile
```

---

## Public API

```python
from rag.generator.generate import generate_answer

answer = generate_answer(
    question="What pH should I target for spirulina?",
    context=format_context(chunks),          # from retrieve.py
    history=state["chat_history"],           # list of {role, content}
    sensor_state={"pH": 9.2, "EC": 28.4},  # optional
    ml_outputs={"growth_rate": "high"},      # optional
)
```

Returns a `str`. Never raises — returns a fallback error message on
LLM failure so the graph always completes.

---

## Model choice rationale

| Role | Model | Why |
|---|---|---|
| Intent router | `llama-3.1-8b-instant` | Fast, sufficient for 4-label classification |
| RAG generator | `llama-3.3-70b-versatile` | Better synthesis from multi-chunk context |
