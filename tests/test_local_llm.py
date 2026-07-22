"""Tests for the local Ollama LLM wiring (2026-07-22) that replaced Groq
across all three roles: intent router, RAG generator, reasoning agent.

These are real, live calls against a running Ollama server -- there is no
meaningful way to unit-test "does the local model classify/reason
correctly" with a mock. The whole file is skipped (not failed) if Ollama
isn't reachable or the configured model isn't pulled, so it doesn't break
runs on a machine without Ollama set up.

Run:
    .venv313\\Scripts\\python -m pytest tests/test_local_llm.py -v
"""

from __future__ import annotations

import os
import re

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("GENERATOR_MODEL_NAME", "qwen3:8b")

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _ollama_available() -> tuple[bool, str]:
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        names = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL not in names:
            return False, f"Ollama running but {OLLAMA_MODEL!r} not pulled (have: {names})"
        return True, ""
    except Exception as exc:
        return False, f"Ollama not reachable at {OLLAMA_BASE_URL}: {exc}"


_AVAILABLE, _SKIP_REASON = _ollama_available()

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason=_SKIP_REASON)


def _no_think_leak(text: str) -> bool:
    """True if `text` contains no raw <think> reasoning block."""
    return "<think>" not in text and "</think>" not in text


# ---------------------------------------------------------------------------
# Provider resolution -- confirm each role actually builds a ChatOllama when
# configured for ollama, without needing a live call.
# ---------------------------------------------------------------------------

class TestProviderResolution:
    def test_intent_router_resolves_to_ollama(self, monkeypatch):
        monkeypatch.setenv("INTENT_MODEL_PROVIDER", "ollama")
        from agent.intent_router import _get_llm
        from langchain_ollama import ChatOllama
        llm = _get_llm()
        assert isinstance(llm, ChatOllama)
        assert llm.reasoning is False  # thinking mode must stay off here

    def test_generator_resolves_to_ollama(self, monkeypatch):
        monkeypatch.setenv("GENERATOR_MODEL_PROVIDER", "ollama")
        import rag.generator.generate as gen
        gen.GENERATOR_PROVIDER = "ollama"
        gen._get_llm.cache_clear()
        from langchain_ollama import ChatOllama
        llm = gen._get_llm()
        assert isinstance(llm, ChatOllama)
        gen._get_llm.cache_clear()

    def test_reasoning_llm_resolves_to_ollama_not_hardcoded_openrouter(self, monkeypatch):
        """Regression test: _get_reasoning_llm() used to be hardcoded to
        OpenRouter with no provider branching at all -- every call failed
        without OPENROUTER_API_KEY, silently degrading every alert to the
        bare fallback template. Confirms it now honours the provider."""
        monkeypatch.setenv("REASONING_MODEL_PROVIDER", "ollama")
        import rag.generator.generate as gen
        gen.REASONING_PROVIDER = "ollama"
        gen._get_reasoning_llm.cache_clear()
        from langchain_ollama import ChatOllama
        llm = gen._get_reasoning_llm()
        assert isinstance(llm, ChatOllama)
        gen._get_reasoning_llm.cache_clear()


# ---------------------------------------------------------------------------
# Intent router -- live accuracy check, reusing the existing 30-case suite
# ---------------------------------------------------------------------------

class TestIntentRouterAccuracy:
    def test_classification_accuracy_at_least_70_percent(self, monkeypatch):
        """Local 8B models are weaker classifiers than Groq's cloud 70B --
        70% (vs the documented 90% baseline on llama-3.1-8b-instant, see
        MEMORY.md) is a reasonable bar that still catches a broken model/
        prompt/parsing regression without being flaky over model updates."""
        monkeypatch.setenv("INTENT_MODEL_PROVIDER", "ollama")
        from agent.intent_router import classify_intent, reset_chain
        from tests.test_intent_router import TEST_CASES, _make_state
        reset_chain()

        passed = 0
        failures = []
        for message, expected in TEST_CASES:
            out = classify_intent(_make_state(message))
            if out["intent"] == expected:
                passed += 1
            else:
                failures.append((message, expected, out["intent"], out["confidence"]))

        reset_chain()  # don't leak an ollama-bound chain into other tests
        accuracy = passed / len(TEST_CASES)
        if failures:
            print(f"\n{len(failures)} misclassified:")
            for msg, exp, got, conf in failures:
                print(f"  expected {exp}, got {got} ({conf:.2f}): {msg[:60]}")
        assert accuracy >= 0.70, f"accuracy {accuracy:.0%} below 70% floor"

    def test_no_empty_response_from_thinking_mode(self, monkeypatch):
        """Regression test for the exact bug found 2026-07-22: qwen3's
        thinking mode consumed the whole num_predict budget on <think>
        content before ever emitting the JSON answer, so classify_intent
        silently returned UNKNOWN/0.0 with raw='' -- not an exception, just
        wrong. reasoning=False on the ChatOllama client fixes it; this
        guards against that regressing back to an empty completion."""
        monkeypatch.setenv("INTENT_MODEL_PROVIDER", "ollama")
        from agent.intent_router import classify_intent, reset_chain
        reset_chain()
        out = classify_intent({"chat_history": [{"role": "user", "content": "what alerts have fired?"}]})
        reset_chain()
        assert out["intent"] != "UNKNOWN" or out["confidence"] > 0.0, (
            "got UNKNOWN/0.0 -- likely an empty completion (thinking-mode token starvation)"
        )


# ---------------------------------------------------------------------------
# RAG generator (generate_answer) -- KNOWLEDGE/UPDATE path
# ---------------------------------------------------------------------------

class TestGenerateAnswer:
    def test_grounded_answer_no_think_leak(self, monkeypatch):
        monkeypatch.setenv("GENERATOR_MODEL_PROVIDER", "ollama")
        import rag.generator.generate as gen
        gen.GENERATOR_PROVIDER = "ollama"
        gen._get_llm.cache_clear()
        gen.get_generator_chain.cache_clear()

        answer = gen.generate_answer(
            question="What pH range is optimal for spirulina platensis?",
            context="Spirulina platensis grows best in an alkaline medium, "
                    "pH 9.5 to 10.5, which also suppresses contaminant algae.",
        )
        gen._get_llm.cache_clear()
        gen.get_generator_chain.cache_clear()

        assert answer.strip()
        assert _no_think_leak(answer)
        assert "9.5" in answer or "10.5" in answer or "pH" in answer.lower()


# ---------------------------------------------------------------------------
# Reasoning agent -- full ReAct tool-calling loop
# ---------------------------------------------------------------------------

class TestReasoningAgent:
    def test_agentic_tool_call_and_no_think_leak(self, monkeypatch):
        """Drives agent.nodes.reasoning_agent directly (not the full graph)
        with a question that should trigger get_recent_alerts, confirming
        Ollama tool-calling actually works end-to-end and that neither the
        plan nor the final response leak raw <think> content."""
        monkeypatch.setenv("GENERATOR_MODEL_PROVIDER", "ollama")
        from agent.nodes import reasoning_agent

        state = {
            "user_id": "test-local-llm",
            "container_id": "container-01",
            "has_container": True,
            "chat_history": [{"role": "user", "content": "have any alerts fired for my container recently?"}],
            "rag_context": "",
            "last_sensor_state": {},
            "ml_outputs": {},
        }
        result = reasoning_agent(state)

        assert result["response"].strip()
        assert _no_think_leak(result["response"])
        assert _no_think_leak(result.get("plan", ""))
        tool_names = [tc["tool"] for tc in result.get("tool_calls", [])]
        assert "get_recent_alerts" in tool_names, f"expected get_recent_alerts, got tools: {tool_names}"


# ---------------------------------------------------------------------------
# reasoning_generate -- proactive alert-text path (agent.monitor uses this)
# ---------------------------------------------------------------------------

class TestReasoningGenerate:
    def test_alert_text_no_think_leak(self, monkeypatch):
        monkeypatch.setenv("REASONING_MODEL_PROVIDER", "ollama")
        import rag.generator.generate as gen
        gen.REASONING_PROVIDER = "ollama"
        gen._get_reasoning_llm.cache_clear()
        gen.get_reasoning_chain.cache_clear()

        text = gen.reasoning_generate(
            question="pH has crashed to 7.0, EC is normal at 20 mS/cm. What should the operator do?",
            context="Spirulina platensis requires pH 9.5-10.5. A pH below 8.5 is critical and often "
                    "indicates CO2 over-injection or contamination; add NaHCO3 to raise pH.",
            sensor_state={"pH": 7.0, "EC": 20.0, "temperature": 36.0},
        )
        gen._get_reasoning_llm.cache_clear()
        gen.get_reasoning_chain.cache_clear()

        assert text.strip()
        assert _no_think_leak(text)


# ---------------------------------------------------------------------------
# Full graph, end to end
# ---------------------------------------------------------------------------

class TestFullGraph:
    def test_graph_invoke_completes_with_container(self, monkeypatch):
        """Same shape as agent/graph.py's own __main__ smoke test, but with
        a REAL (unmocked) intent classification call, exercising the whole
        pipeline against Ollama: check_container -> classify_intent ->
        retrieve_rag -> read_sensors -> run_ml_models -> generator/reasoning
        -> format_response."""
        monkeypatch.setenv("INTENT_MODEL_PROVIDER", "ollama")
        monkeypatch.setenv("GENERATOR_MODEL_PROVIDER", "ollama")
        from agent.graph import graph

        result = graph.invoke({
            "user_id": "test-local-llm-graph",
            "container_id": "container-01",
            "tier": "pro",
            "chat_history": [{"role": "user", "content": "What pH is best for spirulina?"}],
        })

        assert result.get("response", "").strip()
        assert _no_think_leak(result["response"])
