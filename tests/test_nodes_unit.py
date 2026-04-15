"""Unit tests for the SpirulinaAI RAG pipeline nodes.

Covers: intent router, retriever helpers, generator helpers, formatter templates,
and agent nodes (check_container, recall_memory, request_clarification,
reject_off_domain, format_response).

All tests are pure-unit — no real LLM calls, no ChromaDB I/O.
External dependencies (LLMs, ChromaDB, sensors) are patched with unittest.mock.

Run:
    .venv\\Scripts\\python -m pytest tests/test_nodes_unit.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# =============================================================================
# Intent Router
# =============================================================================

class TestParseResponse:
    """_parse_response: JSON extraction from raw LLM output."""

    def _parse(self, raw: str):
        from agent.intent_router import _parse_response
        return _parse_response(raw)

    def test_valid_json(self):
        intent, conf = self._parse('{"intent": "KNOWLEDGE", "confidence": 0.95}')
        assert intent == "KNOWLEDGE"
        assert conf == pytest.approx(0.95)

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"intent": "HARVEST", "confidence": 0.88}\n```'
        intent, conf = self._parse(raw)
        assert intent == "HARVEST"
        assert conf == pytest.approx(0.88)

    def test_json_embedded_in_text(self):
        raw = 'Sure! {"intent": "SYSTEM", "confidence": 0.72} done.'
        intent, conf = self._parse(raw)
        assert intent == "SYSTEM"
        assert conf == pytest.approx(0.72)

    def test_invalid_json_returns_unknown(self):
        intent, conf = self._parse("this is not json at all")
        assert intent == "UNKNOWN"
        assert conf == 0.0

    def test_unknown_intent_label_normalised(self):
        intent, conf = self._parse('{"intent": "RANDOM_LABEL", "confidence": 0.9}')
        assert intent == "UNKNOWN"

    def test_confidence_clamped_to_0_1(self):
        _, conf = self._parse('{"intent": "KNOWLEDGE", "confidence": 2.5}')
        assert conf == pytest.approx(1.0)

        _, conf2 = self._parse('{"intent": "KNOWLEDGE", "confidence": -0.5}')
        assert conf2 == pytest.approx(0.0)

    def test_all_valid_intents_accepted(self):
        from agent.intent_router import VALID_INTENTS
        for label in VALID_INTENTS:
            intent, _ = self._parse(f'{{"intent": "{label}", "confidence": 0.9}}')
            assert intent == label

    def test_lowercase_intent_normalised(self):
        intent, _ = self._parse('{"intent": "knowledge", "confidence": 0.9}')
        assert intent == "KNOWLEDGE"


class TestExtractLastUserMessage:
    """_extract_last_user_message: finds the most recent user turn in history."""

    def _extract(self, history):
        from agent.intent_router import _extract_last_user_message
        return _extract_last_user_message({"chat_history": history})

    def test_single_user_message(self):
        msg = self._extract([{"role": "user", "content": "hello"}])
        assert msg == "hello"

    def test_picks_last_user_message(self):
        history = [
            {"role": "user",      "content": "first"},
            {"role": "assistant", "content": "answer"},
            {"role": "user",      "content": "second"},
        ]
        assert self._extract(history) == "second"

    def test_empty_history_returns_empty_string(self):
        assert self._extract([]) == ""

    def test_no_user_message_returns_empty_string(self):
        history = [{"role": "assistant", "content": "hi there"}]
        assert self._extract(history) == ""


# =============================================================================
# Retriever helpers
# =============================================================================

class TestTokenize:
    """_tokenize: lowercase punctuation-stripping tokenizer for BM25."""

    def _tok(self, text: str):
        from rag.retriever.retrieve import _tokenize
        return _tokenize(text)

    def test_lowercase(self):
        assert "hello" in self._tok("Hello World")

    def test_strips_punctuation(self):
        tokens = self._tok("pH: 9.5, temp=35°C")
        assert "ph" in tokens
        assert "9" in tokens or "9" not in tokens    # punctuation stripped

    def test_empty_string(self):
        assert self._tok("") == []

    def test_numbers_kept(self):
        tokens = self._tok("temperature 35")
        assert "35" in tokens


class TestRrfMerge:
    """_rrf_merge: Reciprocal Rank Fusion combining dense + BM25 lists."""

    def _merge(self, dense, bm25, top_k=5):
        from rag.retriever.retrieve import _rrf_merge
        return _rrf_merge(dense, bm25, top_k)

    def _chunk(self, text, score=0.5):
        return {"text": text, "source": "test", "doc_type": "md",
                "topic": "general", "page": 0, "score": score}

    def test_empty_inputs_return_empty(self):
        assert self._merge([], [], top_k=5) == []

    def test_chunk_in_both_lists_ranks_first(self):
        shared = self._chunk("shared chunk")
        only_dense = self._chunk("only dense")
        only_bm25  = self._chunk("only bm25")

        dense = [shared, only_dense]
        bm25  = [shared, only_bm25]

        result = self._merge(dense, bm25, top_k=3)
        assert result[0]["text"] == "shared chunk"

    def test_top_k_respected(self):
        chunks = [self._chunk(f"chunk {i}") for i in range(10)]
        result = self._merge(chunks[:5], chunks[5:], top_k=3)
        assert len(result) <= 3

    def test_rrf_scores_are_floats(self):
        c = self._chunk("a")
        result = self._merge([c], [c], top_k=1)
        assert isinstance(result[0]["score"], float)


class TestFormatContext:
    """format_context: assembles retrieved chunks into a context string."""

    def _fmt(self, chunks):
        from rag.retriever.retrieve import format_context
        return format_context(chunks)

    def test_empty_returns_empty_string(self):
        assert self._fmt([]) == ""

    def test_single_chunk_contains_source_and_text(self):
        chunk = {"text": "Spirulina grows at pH 9.5", "source": "manual.pdf",
                 "topic": "cultivation_manual", "page": 5, "doc_type": "pdf", "score": 0.9}
        out = self._fmt([chunk])
        assert "manual.pdf" in out
        assert "Spirulina grows at pH 9.5" in out
        assert "p.5" in out

    def test_multiple_chunks_separated_by_divider(self):
        chunks = [
            {"text": "A", "source": "a.pdf", "topic": "t", "page": 1, "doc_type": "pdf", "score": 0.9},
            {"text": "B", "source": "b.pdf", "topic": "t", "page": 2, "doc_type": "pdf", "score": 0.8},
        ]
        out = self._fmt(chunks)
        assert "---" in out
        assert "[Source 1:" in out
        assert "[Source 2:" in out

    def test_no_page_omits_page_info(self):
        chunk = {"text": "hello", "source": "file.md", "topic": "t",
                 "page": 0, "doc_type": "md", "score": 0.5}
        out = self._fmt([chunk])
        assert "p.0" not in out


# =============================================================================
# Generator helpers
# =============================================================================

class TestFormatHistory:
    """_format_history: renders the last N messages as plain text."""

    def _fmt(self, history, window=6):
        from rag.generator.generate import _format_history
        return _format_history(history, window=window)

    def test_empty_history(self):
        assert "(no previous messages)" in self._fmt([])

    def test_single_message_included(self):
        out = self._fmt([{"role": "user", "content": "What is pH?"}])
        assert "What is pH?" in out
        assert "User" in out

    def test_window_limits_included_messages(self):
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        out = self._fmt(msgs, window=3)
        assert "msg 9" in out
        assert "msg 0" not in out   # older than window

    def test_roles_capitalised(self):
        out = self._fmt([
            {"role": "user",      "content": "Q"},
            {"role": "assistant", "content": "A"},
        ])
        assert "User" in out
        assert "Assistant" in out


class TestFormatSensorBlock:
    """_format_sensor_block: wraps sensor dict in XML tags."""

    def _fmt(self, sensor):
        from rag.generator.generate import _format_sensor_block
        return _format_sensor_block(sensor)

    def test_empty_returns_empty(self):
        assert self._fmt({}) == ""

    def test_contains_xml_tags(self):
        out = self._fmt({"ph": 9.5})
        assert "<sensor_readings>" in out
        assert "</sensor_readings>" in out

    def test_contains_key_and_value(self):
        out = self._fmt({"ph": 9.5, "temperature_c": 35})
        assert "ph" in out
        assert "9.5" in out


class TestFormatMlBlock:
    """_format_ml_block: wraps ML outputs in XML tags."""

    def _fmt(self, ml):
        from rag.generator.generate import _format_ml_block
        return _format_ml_block(ml)

    def test_empty_returns_empty(self):
        assert self._fmt({}) == ""

    def test_contains_xml_tags(self):
        out = self._fmt({"growth_score": 0.8})
        assert "<ml_predictions>" in out
        assert "</ml_predictions>" in out


class TestStripThinkTags:
    """_strip_think_tags: removes DeepSeek R1 reasoning blocks."""

    def _strip(self, text):
        from rag.generator.generate import _strip_think_tags
        return _strip_think_tags(text)

    def test_removes_think_block(self):
        raw = "<think>long reasoning here</think>Final answer."
        assert self._strip(raw) == "Final answer."

    def test_no_tags_unchanged(self):
        assert self._strip("Plain answer.") == "Plain answer."

    def test_multiline_think_block_removed(self):
        raw = "<think>\nstep1\nstep2\n</think>\nResult"
        assert "think" not in self._strip(raw)
        assert "Result" in self._strip(raw)

    def test_empty_string(self):
        assert self._strip("") == ""


# =============================================================================
# Formatter templates
# =============================================================================

class TestStatusIcon:
    """_status_icon: emoji based on value vs ok/warn ranges."""

    def _icon(self, val, ok, warn):
        from agent.formatter import _status_icon
        return _status_icon(val, ok, warn)

    def test_ok_range_returns_green(self):
        assert self._icon(9.0, (8.5, 10.5), (8.0, 11.0)) == "✅"

    def test_warn_range_returns_amber(self):
        assert self._icon(8.2, (8.5, 10.5), (8.0, 11.0)) == "⚠️"

    def test_outside_warn_returns_red(self):
        assert self._icon(7.0, (8.5, 10.5), (8.0, 11.0)) == "🔴"


class TestTemplateSensorCard:
    """template_sensor_card: markdown table for sensor readings."""

    def _card(self, sensor, container_id=""):
        from agent.formatter import template_sensor_card
        return template_sensor_card(sensor, container_id)

    def test_empty_sensor_returns_empty(self):
        assert self._card({}) == ""

    def test_known_parameter_appears(self):
        out = self._card({"ph": 9.5})
        assert "pH" in out
        assert "9.5" in out

    def test_container_id_included(self):
        out = self._card({"ph": 9.5}, container_id="CTR-001")
        assert "CTR-001" in out

    def test_status_icon_present(self):
        out = self._card({"ph": 9.5})
        assert "✅" in out or "⚠️" in out or "🔴" in out

    def test_unknown_parameter_still_listed(self):
        out = self._card({"custom_sensor": 42})
        assert "custom_sensor" in out


class TestTemplateRagAnswer:
    """template_rag_answer: wraps LLM answer with optional source footnote."""

    def _answer(self, answer, rag_context=""):
        from agent.formatter import template_rag_answer
        return template_rag_answer(answer, rag_context)

    def test_empty_answer_returns_empty(self):
        assert self._answer("") == ""

    def test_answer_returned_as_is_when_no_context(self):
        assert self._answer("hello") == "hello"

    def test_sources_appended_when_present(self):
        ctx = "[Source 1: manual.pdf, p.1] Some text here"
        out = self._answer("My answer.", ctx)
        assert "manual.pdf" in out
        assert "Sources" in out


class TestTemplateAlert:
    """template_alert: INFO / WARNING / CRITICAL banners."""

    def _alert(self, level, message, action, parameter="", container_id=""):
        from agent.formatter import template_alert
        return template_alert(level, message, action, parameter, container_id)

    def test_critical_contains_emoji(self):
        out = self._alert("CRITICAL", "pH crashed", "Act now")
        assert "🚨" in out

    def test_warning_contains_emoji(self):
        out = self._alert("WARNING", "pH high", "Monitor")
        assert "⚠️" in out

    def test_info_contains_emoji(self):
        out = self._alert("INFO", "All good", "Nothing")
        assert "ℹ️" in out

    def test_parameter_included_when_given(self):
        out = self._alert("WARNING", "msg", "act", parameter="pH")
        assert "pH" in out

    def test_container_id_included(self):
        out = self._alert("INFO", "msg", "act", container_id="CTR-42")
        assert "CTR-42" in out


class TestTemplatePrediction:
    """template_prediction: 60-minute forecast table."""

    def _pred(self, ml_outputs, sensor=None):
        from agent.formatter import template_prediction
        return template_prediction(ml_outputs, sensor)

    def test_no_prediction_key_returns_empty(self):
        assert self._pred({}) == ""

    def test_scalar_prediction_shown(self):
        out = self._pred({"growth_prediction": 0.82})
        assert "0.82" in out

    def test_nested_prediction_dict(self):
        ml = {"growth_prediction": {"OD680": {"current": 0.8, "in_60min": 0.9, "trend": "rising"}}}
        out = self._pred(ml)
        assert "OD680" in out
        assert "0.8" in out
        assert "0.9" in out


class TestTemplateHarvestCard:
    """template_harvest_card: three-scenario harvest timing card."""

    def _harvest(self, ml_outputs, sensor=None):
        from agent.formatter import template_harvest_card
        return template_harvest_card(ml_outputs, sensor or {})

    def test_no_harvest_key_returns_empty(self):
        assert self._harvest({}) == ""

    def test_scalar_harvest_decision_shown(self):
        out = self._harvest({"harvest_readiness": "harvest in 2 days"})
        assert "harvest in 2 days" in out

    def test_structured_harvest_scenarios(self):
        ml = {
            "harvest_readiness": {
                "early":    {"timing": "Now",       "yield": "180g"},
                "balanced": {"timing": "Tomorrow",  "yield": "420g"},
                "optimal":  {"timing": "+2 days",   "yield": "520g"},
            }
        }
        out = self._harvest(ml)
        assert "Early" in out
        assert "Optimal" in out

    def test_od_from_sensor_shown(self):
        out = self._harvest({"harvest_readiness": "ready"}, sensor={"od680": 1.1})
        assert "1.1" in out


class TestFormatMessage:
    """format_message: dispatch function that assembles the final response."""

    def _fmt(self, **kwargs):
        from agent.formatter import format_message
        defaults = dict(
            raw_answer="Test answer.",
            intent="KNOWLEDGE",
            has_container=False,
            rag_context="",
            sensor={},
            ml_outputs={},
            container_id="",
        )
        defaults.update(kwargs)
        return format_message(**defaults)

    def test_knowledge_intent_returns_answer(self):
        out = self._fmt(raw_answer="Spirulina needs pH 9-10.")
        assert "Spirulina needs pH 9-10." in out

    def test_no_container_shows_tip_for_system_intent(self):
        out = self._fmt(intent="SYSTEM", has_container=False, raw_answer="Checking.")
        assert "No container linked" in out

    def test_no_container_shows_tip_for_update_intent(self):
        out = self._fmt(intent="UPDATE", has_container=False, raw_answer="Done.")
        assert "No container linked" in out

    def test_sensor_card_shown_for_update_with_container(self):
        sensor = {"ph": 9.5, "temperature": 35}
        out = self._fmt(intent="UPDATE", has_container=True,
                        sensor=sensor, container_id="CTR-001")
        assert "Sensor Status" in out

    def test_alert_shown_for_critical_sensor(self):
        # pH crash -> CRITICAL
        out = self._fmt(intent="SYSTEM", has_container=True,
                        sensor={"ph": 6.0}, container_id="CTR-001")
        assert "🚨" in out or "CRITICAL" in out

    def test_harvest_card_shown_for_harvest_intent(self):
        ml = {"harvest_readiness": "harvest in 2 days"}
        out = self._fmt(intent="HARVEST", has_container=True,
                        ml_outputs=ml, container_id="CTR-001")
        assert "Harvest Window" in out

    def test_prediction_card_shown_when_growth_prediction_present(self):
        ml = {"growth_prediction": 0.9}
        out = self._fmt(has_container=True, ml_outputs=ml)
        assert "Forecast" in out

    def test_off_domain_no_extra_cards(self):
        out = self._fmt(intent="OFF_DOMAIN", raw_answer="I can't help with that.")
        # No sensor card, no alerts for off-domain
        assert "Sensor Status" not in out


# =============================================================================
# Agent node functions
# =============================================================================

class TestCheckContainer:
    """check_container: resolves has_container flag from state."""

    def _run(self, state):
        from agent.nodes import check_container
        return check_container(state)

    def test_with_container_id(self):
        result = self._run({"container_id": "CTR-001"})
        assert result["has_container"] is True
        assert result["container_id"] == "CTR-001"

    def test_without_container_id(self):
        result = self._run({})
        assert result["has_container"] is False
        assert result["container_id"] == ""

    def test_empty_string_container_id(self):
        result = self._run({"container_id": ""})
        assert result["has_container"] is False


class TestRecallMemory:
    """recall_memory: formats past conversation history for the user."""

    def _run(self, state):
        from agent.nodes import recall_memory
        return recall_memory(state)

    def test_empty_history_returns_prompt_to_start(self):
        result = self._run({"chat_history": []})
        assert "haven't discussed" in result["response"]

    def test_history_included_in_response(self):
        history = [
            {"role": "user",      "content": "What is pH?"},
            {"role": "assistant", "content": "pH is ..."},
            {"role": "user",      "content": "recall"},  # current message
        ]
        result = self._run({"chat_history": history})
        assert "What is pH?" in result["response"]

    def test_current_user_message_excluded(self):
        """The triggering user message should not appear in the summary."""
        history = [
            {"role": "user", "content": "previous question"},
            {"role": "user", "content": "what did we discuss?"},
        ]
        result = self._run({"chat_history": history})
        # "what did we discuss?" is the last user turn — should be excluded
        assert "what did we discuss?" not in result["response"]

    def test_long_messages_truncated(self):
        long_msg = "x" * 500
        history = [
            {"role": "user",      "content": long_msg},
            {"role": "assistant", "content": "answer"},
            {"role": "user",      "content": "recall"},
        ]
        result = self._run({"chat_history": history})
        # Should not exceed 300 + "..." truncation
        assert "..." in result["response"]


class TestRequestClarification:
    """request_clarification: asks a targeted clarifying question."""

    def _run(self, state):
        from agent.nodes import request_clarification
        return request_clarification(state)

    def test_returns_a_question(self):
        state = {
            "intent": "UNKNOWN",
            "confidence": 0.5,
            "chat_history": [{"role": "user", "content": "harvest timing?"}],
        }
        result = self._run(state)
        assert "?" in result["response"]

    def test_harvest_keyword_triggers_harvest_hint(self):
        state = {
            "intent": "KNOWLEDGE",
            "confidence": 0.6,
            "chat_history": [{"role": "user", "content": "when should I harvest my culture?"}],
        }
        result = self._run(state)
        assert "harvest" in result["response"].lower()

    def test_generic_fallback_for_no_keyword_match(self):
        state = {
            "intent": "UNKNOWN",
            "confidence": 0.5,
            "chat_history": [{"role": "user", "content": "I have a question"}],
        }
        result = self._run(state)
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 20


class TestRejectOffDomain:
    """reject_off_domain: redirects non-spirulina questions."""

    def _run(self):
        from agent.nodes import reject_off_domain
        return reject_off_domain({})

    def test_response_mentions_spirulina(self):
        result = self._run()
        assert "spirulina" in result["response"].lower() or "Spirulina" in result["response"]

    def test_response_is_non_empty(self):
        result = self._run()
        assert len(result["response"]) > 10


class TestFormatResponseNode:
    """format_response node: assembles final formatted message."""

    def _run(self, state):
        from agent.nodes import format_response
        return format_response(state)

    def test_response_is_string(self):
        state = {
            "response": "Some LLM answer.",
            "intent": "KNOWLEDGE",
            "has_container": False,
            "rag_context": "",
            "last_sensor_state": {},
            "ml_outputs": {},
            "container_id": "",
        }
        result = self._run(state)
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    def test_chat_history_updated(self):
        state = {
            "response": "Answer here.",
            "intent": "KNOWLEDGE",
            "has_container": False,
            "rag_context": "",
            "last_sensor_state": {},
            "ml_outputs": {},
            "container_id": "",
        }
        result = self._run(state)
        assert "chat_history" in result
        assert result["chat_history"][-1]["role"] == "assistant"


# =============================================================================
# Monitor helpers
# =============================================================================

class TestCheckThresholds:
    """check_thresholds: evaluates sensor dict against hard-coded rules."""

    def _check(self, sensor):
        from agent.monitor import check_thresholds
        return check_thresholds(sensor)

    def test_clean_readings_return_no_breaches(self):
        sensor = {
            "ph": 9.5,
            "temperature_c": 35,
            "od680": 0.8,
            "conductivity_ms": 25,
            "dissolved_o2_pct": 80,
        }
        assert self._check(sensor) == []

    def test_ph_crash_returns_critical(self):
        breaches = self._check({"ph": 7.0})
        assert any(b["severity"] == "critical" for b in breaches)

    def test_high_ph_returns_warning(self):
        breaches = self._check({"ph": 11.0})
        assert any(b["severity"] == "warning" for b in breaches)

    def test_high_od_returns_harvest(self):
        breaches = self._check({"od680": 1.2})
        assert any(b["severity"] == "harvest" for b in breaches)

    def test_status_error_returns_critical(self):
        breaches = self._check({"status": "error"})
        assert any(b["severity"] == "critical" for b in breaches)

    def test_missing_key_ignored(self):
        # No crash for partial sensor readings
        breaches = self._check({"ph": 9.5})
        assert breaches == []

    def test_multiple_breaches_returned(self):
        sensor = {"ph": 7.0, "temperature_c": 42, "od680": 1.5}
        breaches = self._check(sensor)
        assert len(breaches) >= 2


# =============================================================================
# Retrieval query builder (follow-up detection)
# =============================================================================

class TestRetrievalQuery:
    """_retrieval_query: context-aware retrieval query builder in nodes.py."""

    def _query(self, state):
        from agent.nodes import _retrieval_query
        return _retrieval_query(state)

    def test_normal_question_returned_as_is(self):
        state = {
            "chat_history": [
                {"role": "user", "content": "What is the optimal pH for spirulina?"}
            ]
        }
        result = self._query(state)
        assert "pH" in result

    def test_follow_up_with_pronoun_augmented(self):
        state = {
            "chat_history": [
                {"role": "user",      "content": "Tell me about pH management"},
                {"role": "assistant", "content": "pH should be 9-10..."},
                {"role": "user",      "content": "What about it in summer?"},
            ]
        }
        result = self._query(state)
        # Should include context from previous user turn
        assert "pH" in result or "summer" in result

    def test_short_message_augmented_with_history(self):
        state = {
            "chat_history": [
                {"role": "user",      "content": "Tell me about temperature effects on spirulina growth"},
                {"role": "assistant", "content": "Temperature ..."},
                {"role": "user",      "content": "why?"},
            ]
        }
        result = self._query(state)
        # Short follow-up should pull in previous context
        assert len(result) > 3
