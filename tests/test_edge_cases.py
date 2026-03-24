"""Edge case tests — 5 scenarios that require special handling.

Edge case 1: Ambiguous intent (confidence < 0.7)
    -> request_clarification fires, asks one targeted question, RAG skipped.

Edge case 2: Account exists but no container linked
    -> RAG-only mode, response includes a "link a container" tip for
       UPDATE / HARVEST / SYSTEM intents.

Edge case 3: Question outside the spirulina domain
    -> reject_off_domain fires, polite redirect, RAG skipped.

Edge case 4: Very long question (> 400 chars)
    -> retrieve_rag runs (summarizer compresses query before retrieval),
       full answer still generated from the original question.

Edge case 5: User asks about their past conversation
    -> recall_memory fires, history returned, RAG/ML skipped.

Run:
    .venv\\Scripts\\python -m tests.test_edge_cases
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_chain(intent: str, confidence: float) -> MagicMock:
    chain = MagicMock()
    chain.invoke.return_value = f'{{"intent": "{intent}", "confidence": {confidence}}}'
    return chain


def _run_graph(state: dict, intent: str, confidence: float):
    """Invoke the compiled graph with a mocked LLM intent chain."""
    from agent.graph import graph

    buf = io.StringIO()
    with patch("agent.intent_router._get_chain",
               return_value=_mock_chain(intent, confidence)):
        with contextlib.redirect_stdout(buf):
            result = graph.invoke(state)

    return result, buf.getvalue()


def _state(message: str, container_id: str = "", history: list | None = None) -> dict:
    chat_history = list(history or [])
    chat_history.append({"role": "user", "content": message})
    return {
        "user_id":      "test-user",
        "container_id": container_id,
        "chat_history": chat_history,
    }


# ---------------------------------------------------------------------------
# Edge case 1 — Ambiguous intent → targeted clarifying question
# ---------------------------------------------------------------------------

def test_ambiguous_intent_asks_clarifying_question():
    """Low-confidence classification triggers request_clarification.

    Verifies:
    - RAG / ML nodes are skipped entirely.
    - Response contains a clarifying question (not just "rephrase").
    - When the message contains a relevant keyword, the question is targeted.
    """
    # Generic ambiguous message — no keyword hint → generic clarifying question
    result_generic, output_generic = _run_graph(
        _state("uh i dunno do the thing"),
        intent="UNKNOWN",
        confidence=0.40,
    )
    assert result_generic["confidence"] < 0.7
    assert "node] retrieve_rag"  not in output_generic, "RAG must not run on low confidence"
    assert "node] run_ml_models" not in output_generic, "ML must not run on low confidence"
    assert result_generic.get("response", "") != "", "Response must not be empty"

    # Message contains harvest keyword → targeted harvest question
    result_harvest, output_harvest = _run_graph(
        _state("idk about harvest or something"),
        intent="UNKNOWN",
        confidence=0.45,
    )
    response_lower = result_harvest["response"].lower()
    assert "harvest" in response_lower, \
        f"Targeted clarification should mention 'harvest', got: {result_harvest['response'][:200]}"
    assert "node] retrieve_rag" not in output_harvest

    # Message contains pH keyword → targeted pH question
    result_ph, _ = _run_graph(
        _state("something about ph i think"),
        intent="UNKNOWN",
        confidence=0.50,
    )
    assert "ph" in result_ph["response"].lower(), \
        f"Targeted clarification should mention 'pH', got: {result_ph['response'][:200]}"

    print("PASS  test_ambiguous_intent_asks_clarifying_question")
    print(f"      generic response : {result_generic['response'][:100]}")
    print(f"      harvest response : {result_harvest['response'][:100]}")


# ---------------------------------------------------------------------------
# Edge case 2 — No container linked → RAG-only + clear tip message
# ---------------------------------------------------------------------------

def test_no_container_rag_only_with_tip():
    """Without a container, ML/sensors are skipped and a tip is shown for
    intents that benefit from container data (HARVEST, UPDATE, SYSTEM).
    KNOWLEDGE questions are answered cleanly without the tip.
    """
    from agent.intent_router import CONFIDENCE_THRESHOLD

    # HARVEST intent, no container → should show container tip
    result_harvest, output_harvest = _run_graph(
        _state("Is my culture ready to harvest?", container_id=""),
        intent="HARVEST",
        confidence=0.92,
    )
    assert result_harvest["has_container"] is False
    assert "node] run_ml_models" not in output_harvest, "ML must not run without container"
    assert "node] read_sensors"  not in output_harvest, "Sensors must not run without container"
    assert "container" in result_harvest["response"].lower(), \
        "Response must mention container for HARVEST with no container"

    # UPDATE intent, no container → tip included
    result_update, output_update = _run_graph(
        _state("Set the pH to 9.5", container_id=""),
        intent="UPDATE",
        confidence=0.95,
    )
    assert result_update["has_container"] is False
    assert "container" in result_update["response"].lower(), \
        "Response must include container tip for UPDATE with no container"

    # KNOWLEDGE intent, no container → clean answer, no tip needed
    result_know, _ = _run_graph(
        _state("What is the optimal pH for spirulina?", container_id=""),
        intent="KNOWLEDGE",
        confidence=0.95,
    )
    assert result_know["has_container"] is False
    # KNOWLEDGE responses should NOT have the container tip
    assert "no container linked" not in result_know["response"].lower(), \
        "KNOWLEDGE response should not have the container-link tip"

    print("PASS  test_no_container_rag_only_with_tip")
    print(f"      harvest tip snippet: {result_harvest['response'][-120:]}")


# ---------------------------------------------------------------------------
# Edge case 3 — Off-domain question → polite redirect
# ---------------------------------------------------------------------------

def test_off_domain_redirects_to_spirulina():
    """OFF_DOMAIN intent bypasses RAG entirely and returns a redirect message."""
    result, output = _run_graph(
        _state("What is the weather like in Paris today?"),
        intent="OFF_DOMAIN",
        confidence=0.95,
    )
    assert "node] retrieve_rag"  not in output, "RAG must not run for off-domain question"
    assert "node] run_ml_models" not in output, "ML must not run for off-domain question"

    response_lower = result["response"].lower()
    assert "spirulina" in response_lower, \
        "Off-domain response must redirect to spirulina topic"
    assert any(w in response_lower for w in ["outside", "speciali", "domain", "can't help"]), \
        f"Off-domain response must acknowledge the topic is out of scope: {result['response'][:200]}"

    # Also test a French off-domain question
    result_fr, output_fr = _run_graph(
        _state("Quelle est la recette du couscous?"),
        intent="OFF_DOMAIN",
        confidence=0.92,
    )
    assert "node] retrieve_rag" not in output_fr
    assert "spirulina" in result_fr["response"].lower()

    print("PASS  test_off_domain_redirects_to_spirulina")
    print(f"      response: {result['response'][:150]}")


# ---------------------------------------------------------------------------
# Edge case 4 — Very long question → retrieval uses summarized query
# ---------------------------------------------------------------------------

def test_long_question_uses_summarized_retrieval_query():
    """A question exceeding 400 characters triggers the query summarizer before
    retrieval. The pipeline still completes with a full response.
    """
    long_question = (
        "I have been running my spirulina culture for about 3 weeks now and I am "
        "starting to notice that the growth rate seems to have slowed down significantly "
        "compared to the first two weeks. The color is still blue-green but maybe slightly "
        "less vibrant. I am measuring pH every morning and it is around 9.2, temperature "
        "is at 33 degrees Celsius, and I check the EC which reads about 24 mS/cm. I am "
        "also noticing some small bubbles forming at the surface which I have not seen "
        "before. Could you help me understand what might be causing the slowdown and what "
        "I should check or adjust first to get growth back on track?"
    )
    assert len(long_question) > 400, "Precondition: question must be > 400 chars"

    # Mock the summarizer chain so the test doesn't need a real API call
    mock_summary_chain = MagicMock()
    mock_summary_chain.invoke.return_value = "slow growth causes and fixes spirulina culture"

    with patch("agent.nodes._get_summarizer_chain", return_value=mock_summary_chain):
        result, output = _run_graph(
            _state(long_question, container_id="container-42"),
            intent="KNOWLEDGE",
            confidence=0.90,
        )

    assert "node] retrieve_rag" in output, "RAG must still run for long questions"
    assert result.get("response", "") != "", "Response must not be empty"
    assert mock_summary_chain.invoke.called, "Summarizer must have been called"
    called_with = mock_summary_chain.invoke.call_args[0][0]["question"]
    assert called_with == long_question, "Summarizer must receive the full original question"

    print("PASS  test_long_question_uses_summarized_retrieval_query")
    print(f"      summarizer input length: {len(long_question)} chars")
    print(f"      summarized query: {mock_summary_chain.invoke.return_value}")


# ---------------------------------------------------------------------------
# Edge case 5 — User asks about past conversation → memory returned
# ---------------------------------------------------------------------------

def test_memory_recall_returns_history():
    """MEMORY_RECALL intent routes to recall_memory node which returns
    the conversation history without calling the LLM or RAG.
    """
    prior_history = [
        {"role": "user",      "content": "What is the optimal pH for spirulina?"},
        {"role": "assistant", "content": "The optimal pH range is 8.5 to 10.5."},
        {"role": "user",      "content": "How does temperature affect growth?"},
        {"role": "assistant", "content": "Optimal temperature is 35-37 °C."},
    ]

    result, output = _run_graph(
        _state("What did we discuss earlier?", history=prior_history),
        intent="MEMORY_RECALL",
        confidence=0.93,
    )

    assert "node] retrieve_rag"  not in output, "RAG must not run for memory recall"
    assert "node] run_ml_models" not in output, "ML must not run for memory recall"

    response = result["response"]
    # Must contain content from both prior user turns
    assert "pH" in response or "optimal" in response.lower(), \
        "Memory response must reference first conversation topic"
    assert "temperature" in response.lower() or "35" in response, \
        "Memory response must reference second conversation topic"
    # Current question must NOT appear in the recalled history
    assert "what did we discuss" not in response.lower(), \
        "The triggering recall question must not appear in the history output"

    # Empty history → graceful empty-history message
    result_empty, _ = _run_graph(
        _state("Remind me what I asked before?"),
        intent="MEMORY_RECALL",
        confidence=0.90,
    )
    assert result_empty.get("response", "") != "", "Empty history must return a graceful message"
    assert "node] retrieve_rag" not in _

    print("PASS  test_memory_recall_returns_history")
    print(f"      history snippet: {result['response'][:200]}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_ambiguous_intent_asks_clarifying_question,
        test_no_container_rag_only_with_tip,
        test_off_domain_redirects_to_spirulina,
        test_long_question_uses_summarized_retrieval_query,
        test_memory_recall_returns_history,
    ]

    passed = 0
    failed = 0

    print(f"\nRunning {len(tests)} edge-case tests ...\n")
    print("-" * 65)

    for test in tests:
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                test()
            for line in buf.getvalue().splitlines():
                if line.startswith("PASS") or line.startswith("      "):
                    print(line)
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}")
            print(f"      {exc}")
            failed += 1
        except Exception as exc:
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
        print()

    print("-" * 65)
    print(f"Results: {passed}/{len(tests)} passed\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
