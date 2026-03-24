# tests/test_edge_cases.py

## Purpose
Verifies that all five edge cases are handled correctly without making real LLM API calls. Uses `unittest.mock.patch` to inject controlled intent/confidence values.

## Edge cases covered

| # | Case | Trigger | Expected behavior |
|---|------|---------|------------------|
| 1 | Ambiguous intent | `confidence < 0.7` | `request_clarification` fires; targeted question returned; RAG skipped |
| 2 | No container linked | `has_container=False` + UPDATE/HARVEST/SYSTEM intent | RAG-only mode; container tip appended to response |
| 3 | Off-domain question | `intent=OFF_DOMAIN` | `reject_off_domain` fires; polite redirect; RAG skipped |
| 4 | Very long question (> 400 chars) | `len(message) > 400` | Summarizer called; RAG still runs; full response generated |
| 5 | Memory recall request | `intent=MEMORY_RECALL` | `recall_memory` fires; history returned; RAG/ML skipped |

## Test descriptions

### `test_ambiguous_intent_asks_clarifying_question`
- Low confidence (0.40) → clarification node fires.
- Generic message → generic clarifying question.
- Message with "harvest" keyword → targeted harvest clarification.
- Message with "pH" keyword → targeted pH clarification.
- Asserts RAG and ML nodes did NOT run (checks stdout).

### `test_no_container_rag_only_with_tip`
- HARVEST intent, no container → `has_container=False`, ML/sensors skipped, "container" in response.
- UPDATE intent, no container → container tip present.
- KNOWLEDGE intent, no container → clean answer, no container tip (KNOWLEDGE doesn't need container).

### `test_off_domain_redirects_to_spirulina`
- English off-domain question (weather) → redirect mentions "spirulina" and "outside/speciali*".
- French off-domain question (couscous recipe) → same redirect behavior.
- Asserts RAG did NOT run.

### `test_long_question_uses_summarized_retrieval_query`
- Uses a 600+ char question.
- Mocks `_get_summarizer_chain` to avoid real API calls.
- Asserts summarizer was called with the full original question.
- Asserts RAG still ran and response is not empty.

### `test_memory_recall_returns_history`
- Provides 4 prior conversation messages as history.
- MEMORY_RECALL intent → `recall_memory` fires.
- Asserts both prior topics (pH, temperature) appear in the response.
- Asserts the triggering recall question does NOT appear in the output.
- Asserts empty history case returns graceful message.

## Run
```bash
.venv\Scripts\python -m tests.test_edge_cases
```
Expected: 5/5 passed (no real API keys needed).
