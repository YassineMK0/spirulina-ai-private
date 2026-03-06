"""Unit tests for the conditional routing gate.

Tests both branches without making any LLM API calls:
  Branch A - has_container=True  -> full pipeline (RAG + ML + sensors)
  Branch B - has_container=False -> RAG-only pipeline + friendly message
  Branch C - confidence < 0.7    -> request_clarification, pipeline skipped
  Branch D - check_container node sets has_container correctly

Each node prints "[node] <name>" -- we capture stdout to verify which
nodes actually executed, without touching the compiled graph or mocking
internal references.

Run:
    .venv\\Scripts\\python -m tests.test_routing_gate
"""

from __future__ import annotations

import io
import sys
import contextlib
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_chain(intent: str = "KNOWLEDGE", confidence: float = 0.95) -> MagicMock:
    """Return a mock chain that yields a fixed JSON classification response."""
    chain = MagicMock()
    chain.invoke.return_value = (
        f'{{"intent": "{intent}", "confidence": {confidence}}}'
    )
    return chain


def _make_state(container_id: str, message: str = "What pH is best for spirulina?") -> dict:
    return {
        "user_id": "test-user",
        "container_id": container_id,
        "chat_history": [{"role": "user", "content": message}],
    }


def _run_graph(state: dict, intent: str = "KNOWLEDGE", confidence: float = 0.95):
    """Invoke the graph with a mocked LLM chain. Returns (result, captured_stdout)."""
    from agent.graph import graph

    buf = io.StringIO()
    with patch("agent.intent_router._get_chain",
               return_value=_mock_chain(intent, confidence)):
        with contextlib.redirect_stdout(buf):
            result = graph.invoke(state)

    return result, buf.getvalue()


def _nodes_in(output: str) -> list[str]:
    """Extract node names from captured print output."""
    nodes = []
    for line in output.splitlines():
        if line.startswith("[node] ") or line.startswith("[intent_router]"):
            nodes.append(line.split("]")[0].lstrip("["))
    return nodes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_container_gate_sets_has_container_correctly():
    """check_container node sets has_container=True/False from container_id."""
    from agent.nodes import check_container

    out = check_container({"container_id": "abc-123"})
    assert out["has_container"] is True
    assert out["container_id"] == "abc-123"

    out = check_container({"container_id": ""})
    assert out["has_container"] is False

    out = check_container({})
    assert out["has_container"] is False

    print("PASS test_container_gate_sets_has_container_correctly")


def test_full_pipeline_with_container():
    """has_container=True -> full pipeline: RAG + ML + sensors all run."""
    result, output = _run_graph(_make_state("container-42"))

    assert result["has_container"] is True,  "has_container must be True"
    assert result["intent"] == "KNOWLEDGE",  f"wrong intent: {result['intent']}"
    assert result["confidence"] == 0.95,     f"wrong confidence: {result['confidence']}"

    # All pipeline nodes must appear in stdout
    assert "node] run_ml_models" in output, "run_ml_models must run in full pipeline"
    assert "node] read_sensors"  in output, "read_sensors must run in full pipeline"
    assert "node] retrieve_rag"  in output, "retrieve_rag must run in full pipeline"

    # No-container message must NOT appear
    assert "no container" not in result["response"].lower(), \
        "full-pipeline response should not mention 'no container'"

    # Response must include container id
    assert "container-42" in result["response"], \
        "response should include container_id"

    print("PASS test_full_pipeline_with_container")
    print(f"     nodes executed: {_nodes_in(output)}")
    print(f"     response: {result['response'][:80]}")


def test_rag_only_without_container():
    """has_container=False -> RAG runs, ML/sensors skipped, friendly message shown."""
    result, output = _run_graph(_make_state(""))   # no container

    assert result["has_container"] is False, "has_container must be False"
    assert result["intent"] == "KNOWLEDGE",  f"wrong intent: {result['intent']}"

    # RAG must run; ML and sensors must NOT
    assert "node] retrieve_rag"  in output, "retrieve_rag must run even without container"
    assert "node] run_ml_models" not in output, "run_ml_models must NOT run in RAG-only mode"
    assert "node] read_sensors"  not in output, "read_sensors must NOT run in RAG-only mode"

    # Friendly no-container message must be present
    response_lower = result["response"].lower()
    assert "no container" in response_lower or "link" in response_lower, \
        f"Response must mention container linking:\n{result['response']}"

    print("PASS test_rag_only_without_container")
    print(f"     nodes executed: {_nodes_in(output)}")
    print(f"     response: {result['response'][:120]}")


def test_low_confidence_triggers_clarification():
    """confidence < 0.7 -> request_clarification fires, RAG/ML never run."""
    result, output = _run_graph(
        _make_state("container-42", "uh idk do the thing"),
        intent="UNKNOWN",
        confidence=0.45,
    )

    assert result["confidence"] < 0.7, "confidence must be below threshold"

    # Pipeline must NOT have run
    assert "node] retrieve_rag"  not in output, "retrieve_rag must be skipped on low confidence"
    assert "node] run_ml_models" not in output, "run_ml_models must be skipped on low confidence"

    # Clarification response
    assert "rephrase" in result["response"].lower(), \
        f"Response must ask to rephrase:\n{result['response']}"

    print("PASS test_low_confidence_triggers_clarification")
    print(f"     confidence: {result['confidence']}")
    print(f"     response: {result['response'][:80]}")


def test_no_container_still_classifies_intent():
    """Without a container, intent classification still runs (not skipped)."""
    result, output = _run_graph(_make_state(""), intent="KNOWLEDGE", confidence=0.95)

    # Intent router must have fired
    assert "intent_router" in output, "intent router must run even without container"
    assert result["intent"] == "KNOWLEDGE", f"wrong intent: {result['intent']}"

    print("PASS test_no_container_still_classifies_intent")
    print(f"     intent: {result['intent']}  confidence: {result['confidence']}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_container_gate_sets_has_container_correctly,
        test_full_pipeline_with_container,
        test_rag_only_without_container,
        test_low_confidence_triggers_clarification,
        test_no_container_still_classifies_intent,
    ]

    passed = 0
    failed = 0

    print(f"Running {len(tests)} routing gate tests ...\n")
    print("-" * 60)

    for test in tests:
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                test()
            # Print only the PASS/FAIL lines from the test itself
            for line in buf.getvalue().splitlines():
                if line.startswith("PASS") or line.startswith("     "):
                    print(line)
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}")
            print(f"      {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
        print()

    print("-" * 60)
    print(f"Results: {passed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
