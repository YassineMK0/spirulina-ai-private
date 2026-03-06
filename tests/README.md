# tests/ — Test Suite

Unit tests, integration tests, and evaluation scripts for the pipeline.

---

## Files

### `test_intent_router.py`
30-message eval set covering all 4 intents.
Calls the real Groq API — requires `GROQ_API_KEY` in `.env`.

**Result: 27/30 correct (90% accuracy), 0 low-confidence triggers.**

```bash
.venv/Scripts/python tests/test_intent_router.py
```

---

### `test_routing_gate.py`
5 unit tests for the LangGraph conditional routing gates.
Mocks the LLM chain — no API calls needed.

Tests:
1. Full pipeline fires for container users
2. RAG-only path fires for users without a container
3. Clarification node fires when confidence < 0.7
4. `has_container` gate correctly splits after `retrieve_rag`
5. `classify_intent` always runs regardless of container status

```bash
.venv/Scripts/python -m pytest tests/test_routing_gate.py -v
```

---

### `eval_set.py`
20 hand-written query / keyword pairs used by the retrieval tuner.
5 queries per topic: `scientific_literature`, `cultivation_manual`,
`qa_pairs`, `troubleshooting`.

Each entry has:
- `query` — natural-language question
- `must` — all these keywords must appear in a matching chunk
- `any_of` — at least one synonym must appear
- `topic` — expected source topic
- `note` — description of the test case

Not a runnable test — imported by `tune_retrieval.py` and `test_retrieval.py`.

---

### `test_retrieval.py`
Runs the 20 eval queries against the live ChromaDB collection.
Requires the ingestion pipeline to have been run first.

Pass criterion: best chunk L2 score < 1.5.
Also runs metadata filter spot-checks for all 4 topics.

```bash
.venv/Scripts/python tests/test_retrieval.py
```

---

### `tune_retrieval.py`
Grid search over 18 configurations to find optimal retrieval settings.

Grid:
```
chunk_size  [300, 500, 800]
top_k       [3, 5, 8]
filter      [on, off]
```

- Phase 1: ingests into 3 named collections (`spirulina_kb_300/500/800`)
- Phase 2: evaluates all 20 queries per config, measures hit rate
- Phase 3: prints ranked table, declares winner at >= 80% hit rate

```bash
.venv/Scripts/python tests/tune_retrieval.py
```

---

## Running all tests

```bash
# All unit tests (no API needed)
.venv/Scripts/python -m pytest tests/test_routing_gate.py -v

# Intent router accuracy (needs GROQ_API_KEY)
.venv/Scripts/python tests/test_intent_router.py

# Retrieval quality (needs ingested ChromaDB)
.venv/Scripts/python tests/test_retrieval.py

# Retrieval tuning grid (needs ingested ChromaDB, slow on first run)
.venv/Scripts/python tests/tune_retrieval.py
```
