# SpirulinaAI — Test Suite Documentation

---

## How to run

**Backend (Python):**
```powershell
.venv313\Scripts\pytest tests/ -v
```

**Frontend (Next.js):**
```powershell
cd spirulina-ui
npm test              # run once
npm run test:watch    # re-run on file change
npm run test:coverage # with coverage report
```

---

## Backend Tests (`tests/`)

> `test_ml_models.py` (M1 LSTM / M2 LightGBM / M3 harvest scheduler unit tests)
> was removed along with the old `models/` artifacts it tested. The anomaly
> detector is now `models/anomaly_model/` (rule engine + seasonal check +
> LOF combination model) — see `test_anomaly_model.py` and
> `test_monitor_combination.py` below.

### `test_anomaly_model.py` — M1 Anomaly Detector Unit Tests

Tests `models/anomaly_model/` (rules, seasonal, detector) against the real
trained artifact (fast — no mocking needed, joblib load is <1s).

| Test | What it tests |
|------|--------------|
| `TestEvaluateRulesTurbidite::*` | `evaluate_rules` tolerates a missing/`None` `Turbidite` key instead of `KeyError` (the live agent snapshot never has a calibrated OD680 value) |
| `TestSeasonalResidualZscore::*` | Robust z-score against hour-of-day median/MAD baseline; zero-MAD doesn't divide by zero |
| `TestAnomalyDetectorLoad::*` | `AnomalyDetector.load()` works; combination model's `feature_cols` excludes `Turbidite`; `evaluate()` skips the combination layer when `daily_context` is `None` or incomplete; pH crash → severity 3; clean snapshot → severity 0 |

---

### `test_monitor_combination.py` — 24h Combination-Model Cron Wiring

Integration tests against the real sqlite-backed `sensor_store` (throwaway
container IDs, cleaned up per test) for the pieces added when the LOF
combination model was wired into a daily cron job (`agent/monitor.py`,
`data/store.py`).

| Test | What it tests |
|------|--------------|
| `TestGetSince::*` | `SensorStore.get_since` filters by timestamp, returns oldest-first, and (unlike `get_latest`) doesn't drop rows with partial sensor data |
| `TestBuildDailyContext::*` | `_build_daily_context` returns `None` with <2 readings; builds the exact 12-key feature vector with enough 24h history; normalizes EC from µS/cm to mS/cm |
| `TestRunCombinationModelCheck::*` | No-op with no active sessions or insufficient history; pushes a `severity=warning, source=model-24h` alert when the LOF layer flags an outlier day; repeat calls with the same score are deduped |

---

### `test_local_llm.py` — Local Ollama LLM Wiring

Live integration tests against a running Ollama server (default model
`qwen3:8b`) for the three LLM roles that switched from Groq/OpenRouter to a
local model on 2026-07-22 — see `MEMORY.md` / `local_llm_ollama.md`.
**Whole file auto-skips** (not fails) if Ollama isn't reachable at
`OLLAMA_BASE_URL` or the configured model isn't pulled, so it's safe to run
on a machine without Ollama set up.

| Test | What it tests |
|------|--------------|
| `TestProviderResolution::*` | Each role's `_get_llm()`/`_get_reasoning_llm()` actually builds a `ChatOllama` when its provider env var is `"ollama"`, with `reasoning=False` |
| `TestIntentRouterAccuracy::test_classification_accuracy_at_least_70_percent` | Reuses the 30-case suite from `test_intent_router.py` against Ollama; floor is 70% (vs the ~90% Groq baseline — local 8B models classify a bit worse) |
| `TestIntentRouterAccuracy::test_no_empty_response_from_thinking_mode` | Regression test for the exact bug hit while wiring this in: qwen3's thinking mode burned the whole token budget on `<think>` before ever emitting the JSON answer, silently returning `UNKNOWN/0.0` |
| `TestGenerateAnswer::test_grounded_answer_no_think_leak` | `generate_answer` (KNOWLEDGE/UPDATE path) returns a real, grounded, `<think>`-free answer |
| `TestReasoningAgent::test_agentic_tool_call_and_no_think_leak` | The ReAct tool-calling loop actually calls `get_recent_alerts` via Ollama's native tool-calling, with no `<think>` leakage into the plan panel or final response |
| `TestReasoningGenerate::test_alert_text_no_think_leak` | `reasoning_generate` (used by `agent/monitor.py` for proactive alert text) works — regression test for `_get_reasoning_llm` previously being hardcoded to OpenRouter with no fallback |
| `TestFullGraph::test_graph_invoke_completes_with_container` | The full compiled LangGraph pipeline completes end-to-end against Ollama (unmocked intent classification, unlike `agent/graph.py`'s own `__main__` smoke test) |

---

### `test_api_endpoints.py` — FastAPI Endpoint Integration Tests

Tests all HTTP endpoints using FastAPI's `TestClient`. The LangGraph pipeline, memory store, sensor cache, and ML models are mocked so no external services are required.

**`GET /health`**
| Test | What it tests |
|------|--------------|
| `test_returns_200` | Health endpoint returns HTTP 200 |
| `test_returns_ok_status` | Response body is `{"status": "ok"}` |

**`POST /chat`**
| Test | What it tests |
|------|--------------|
| `test_returns_200_with_valid_payload` | Valid chat request returns HTTP 200 |
| `test_response_contains_expected_fields` | Response has `response`, `content`, `tools_used`, `intent`, `confidence` |
| `test_response_text_matches_graph_output` | Response text comes from the LangGraph output |
| `test_default_tier_is_free` | Tier defaults to `"free"` when not specified |
| `test_pro_tier_forwarded_to_graph` | `tier: "pro"` is forwarded to the graph state |

**`GET /history/{user_id}`**
| Test | What it tests |
|------|--------------|
| `test_returns_stored_history` | Returns the messages stored in memory for a user |
| `test_returns_empty_list_for_new_user` | Returns `[]` when user has no history |

**`DELETE /history/{user_id}`**
| Test | What it tests |
|------|--------------|
| `test_returns_cleared_status` | Returns `{"status": "cleared"}` |
| `test_calls_memory_store_clear` | `memory_store.clear()` is called with the correct user_id |

**`GET /sensors/{container_id}`**
| Test | What it tests |
|------|--------------|
| `test_returns_live_sensor_data_from_mqtt_cache` | Returns live data when MQTT cache has a reading |
| `test_falls_back_to_db_when_mqtt_cache_empty` | Falls back to SQLite when MQTT cache is empty |
| `test_returns_empty_dict_when_no_data` | Returns `{}` when neither MQTT nor DB has data |

**`GET /models/{container_id}`**
| Test | What it tests |
|------|--------------|
| `test_returns_no_data_when_history_empty` | Returns `{"error": "no_data"}` when sensor history is empty |
| `test_returns_m1_m2_m3_keys_on_success` | Response has `m1`, `m2`, `m3` keys when data is available |

---

### `test_nodes_unit.py` — Agent Node Unit Tests *(existing)*

Tests each LangGraph node function in isolation with all LLM and database calls mocked.

Covers: `check_container`, `retrieve_rag`, `run_ml_models`, `read_sensors`, `reasoning_agent`, `request_clarification`, `reject_off_domain`, `recall_memory`, `generate_response`, `format_response` — plus retriever helpers (`_tokenize`, `_rrf_merge`, `format_context`), generator helpers, formatter templates, monitor `check_thresholds`, and query builder `_retrieval_query`.

---

### `test_conversations.py` — Full Pipeline Conversation Tests *(existing)*

50 end-to-end scenario tests across 5 categories that run messages through the full LangGraph pipeline (LLM calls are live against Groq):

- **A (A01–A10):** Pure knowledge questions — pH, temperature, light, nutrients
- **B (B01–B10):** Multi-turn dialogs — follow-ups, memory recall, context continuity
- **C (C01–C10):** Troubleshooting — yellow culture, foam, contamination, EC anomalies
- **D (D01–D10):** Harvest timing — readiness, partial harvest, French language question
- **E (E01–E10):** No-container mode — RAG-only responses without sensor data

Each scenario scores 3 points: intent match (1), non-empty response (1), expected keyword in response (1). Pass threshold is ≥ 2/3.

---

### `test_intent_router.py` — Intent Classification Accuracy *(existing)*

30 messages across 4 intent labels run through whichever classifier
`INTENT_MODEL_PROVIDER` currently points at (Groq `llama-3.1-8b-instant` by
default before 2026-07-22; local `qwen3:8b` via Ollama since — see
`test_local_llm.py` above, which reuses this same `TEST_CASES` list):

- 8 × `KNOWLEDGE` — factual questions about spirulina biology
- 8 × `UPDATE` — parameter change instructions
- 7 × `HARVEST` — harvest readiness questions
- 7 × `SYSTEM` — sensor status and device queries

Reports classification accuracy %. Target: ≥ 90% (Groq baseline); measured
~97% on qwen3:8b in practice, though `test_local_llm.py`'s own floor is a
more conservative 70% to avoid flakiness across model updates.

---

### `test_retrieval.py` — RAG Retrieval Quality *(existing)*

10 queries run through the BM25 + dense hybrid retriever:

- 3 × `scientific_literature` — biology, protein content, growth kinetics
- 2 × `cultivation_manual` — Zarrouk medium, pH control
- 2 × `troubleshooting` — culture problems, diagnosis steps
- 2 × `qa_pairs` — common operational questions
- 1 × French question — multilingual retrieval check

Each query checks that the top retrieved chunks have L2 distance < 1.5 and that metadata filters return the correct `topic` field.

---

### `test_edge_cases.py` — Edge Case Routing *(existing)*

5 specific scenarios that test routing decisions at the boundary of normal operation:

| Scenario | What it tests |
|----------|--------------|
| Ambiguous intent (confidence < 0.70) | Clarification node fires; RAG and ML are skipped |
| No container linked | UPDATE/HARVEST/SYSTEM intents fall back to RAG-only mode |
| Off-domain question | Polite rejection fires; no RAG or LLM generation |
| Very long input (> 400 chars) | Query is compressed before retrieval |
| Memory recall intent | Conversation history is returned without calling RAG |

---

### `ragas_eval.py` — RAG Quality Evaluation *(existing)*

20 questions evaluated with RAGAS metrics using `llama-3.3-70b-versatile` as judge:

- 7 × factual (pH, temperature, OD680, protein, light, EC, nutrients)
- 7 × troubleshooting (yellow color, pH drop, foam, smell, EC high, slow growth, contamination)
- 6 × operational (harvest timing, partial harvest, stirring, drying, refill, French)

**Passing thresholds:**

| Metric | Threshold | Result |
|--------|-----------|--------|
| Relevance | > 0.80 | 0.873 ✓ |
| Faithfulness | > 0.85 | 0.942 ✓ |
| Recall | > 0.70 | 0.767 ✓ |

---

### `latency_profile.py` — Pipeline Latency Profiling *(existing)*

5 questions timed through each RAG pipeline stage: embedding, ChromaDB search, BM25 search, total retrieval, LLM generation, response formatting, and end-to-end total. Target: < 3 seconds end-to-end.

---

## Frontend Tests (`spirulina-ui/__tests__/`)

### `atoms.test.jsx` — UI Atom Component Unit Tests

Tests the 6 primitive components in `components/atoms.jsx` in isolation.

**`Dot`**
| Test | What it tests |
|------|--------------|
| `renders a div` | Component mounts without errors |
| `applies blink animation when blink=true` | `animation` style contains `"blink"` |
| `has no animation when blink=false (default)` | `animation` style is empty by default |
| `uses custom size` | `width` and `height` reflect the `size` prop |
| `uses custom color` | `background` reflects the `color` prop |

**`Tag`**
| Test | What it tests |
|------|--------------|
| `renders children text` | Text content is visible |
| `renders as a span` | Element tag is `SPAN` |

**`Label`**
| Test | What it tests |
|------|--------------|
| `renders children text` | Text content is visible |
| `renders as a div` | Element tag is `DIV` |

**`AgentAvatar`**
| Test | What it tests |
|------|--------------|
| `renders with default size` | Width and height default to 26px |
| `renders with custom size` | Width and height match the `size` prop |
| `contains an SVG icon` | An `<svg>` element is rendered inside |

**`ToolPills`**
| Test | What it tests |
|------|--------------|
| `renders tool names` | Each tool name appears in the DOM |
| `returns null when tools is empty` | Nothing is rendered for an empty array |
| `returns null when tools is undefined` | Nothing is rendered when prop is missing |
| `renders the tool name as-is, with no checkmark prefix` | Each pill displays the tool name unmodified (no `"✓ "` prefix) |

**`SpinnerDots`**
| Test | What it tests |
|------|--------------|
| `renders three dots` | The flex wrapper has exactly 3 child divs |
| `each dot has a blink animation` | Every dot's `animation` style contains `"blink"` |

---

### `api.test.js` — API Module Unit Tests

Tests all 6 functions in `lib/api.js` with `fetch` and `EventSource` fully mocked — no real network calls.

**`sendMessage`**
| Test | What it tests |
|------|--------------|
| `POSTs to /chat with correct body` | Correct URL, method, headers, and JSON body |
| `throws on non-ok response` | `Error("API error 500")` thrown on HTTP error |

**`getHistory`**
| Test | What it tests |
|------|--------------|
| `returns parsed array on success` | Parsed JSON array returned on 200 |
| `returns [] when response is not ok` | Empty array on non-200 response |
| `returns [] on network error` | Empty array on fetch exception (no crash) |

**`clearHistory`**
| Test | What it tests |
|------|--------------|
| `sends DELETE to /history/{userId}` | Correct HTTP method and URL |

**`getModelOutputs`**
| Test | What it tests |
|------|--------------|
| `returns parsed data on success` | M1/M2/M3 data returned on 200 |
| `returns null when response is not ok` | `null` on non-200 response |
| `returns null on network error` | `null` on fetch exception |

**`getSensorData`**
| Test | What it tests |
|------|--------------|
| `returns sensor object on success` | Sensor readings returned on 200 |
| `returns null for empty object response` | `null` when server returns `{}` |
| `returns null on error` | `null` on fetch exception |

**`connectAlerts`**
| Test | What it tests |
|------|--------------|
| `opens EventSource with correct URL including containerId` | URL contains `/alerts/user1` and `container_id=c1` |
| `opens EventSource without container_id param when containerId is empty` | No `container_id` param when empty string passed |
| `calls onConnect when type=connected is received` | `onConnect` callback fires on connection frame |
| `calls onAlert with text when type=alert is received` | `onAlert` receives the alert text string |
| `calls onError when EventSource errors` | `onError` callback fires on SSE error |
| `returns a disconnect function that closes the EventSource` | `es.close()` is called when disconnect function is invoked |
| `silently ignores malformed SSE frames` | No crash or callback on invalid JSON |

---

### `Bubble.test.jsx` — Chat Bubble Integration Tests

Tests the `Bubble` component with all 3 message roles and all content type variants.

**Alert role**
| Test | What it tests |
|------|--------------|
| `renders the alert text` | Alert message text is visible |
| `renders the SSE label` | `"SSE ALERT"` header is shown |
| `renders the timestamp` | Time string is displayed |

**User role**
| Test | What it tests |
|------|--------------|
| `renders the user message text` | Message text is visible |
| `renders the timestamp` | Time string is displayed |

**Agent role — text content**
| Test | What it tests |
|------|--------------|
| `renders the agent response text` | Response text is visible |
| `renders the AgentAvatar (SVG)` | An `<svg>` icon is rendered |

**Agent role — tool pills**
| Test | What it tests |
|------|--------------|
| `renders tool pill names` | Each tool name appears with a checkmark |

**Agent role — diagnosis content**
| Test | What it tests |
|------|--------------|
| `renders root cause text` | `content.cause` text is visible |
| `renders sensor labels` | EC alert sensor shows `"EC ▲"`, pH normal sensor shows `"pH"` with no suffix |
| `renders the recommended action` | Action section header and dose appear |

**Agent role — harvest content**
| Test | What it tests |
|------|--------------|
| `renders the best day recommendation header` | `"Wait — harvest tomorrow"` header is shown |
| `renders the 3-day harvest percentages` | Today/tomorrow/day-after percentages are displayed |
| `renders the M3 recommendation text` | Recommendation string is visible |
| `renders turbidity forecast section` | M2 turbidity forecast section is rendered |
| `renders "Culture not ready" when harvest_pct is 0 for all days` | Not-ready state shows correct message |

**Unknown role**
| Test | What it tests |
|------|--------------|
| `renders nothing for unknown roles` | `null` is rendered — no crash |

---

### `AlertsPage.test.jsx` — Alerts Page Integration Tests

Tests the `AlertsPage` component for empty state, alert rendering, severity styles, active/past tagging, and user interactions.

**Empty state**
| Test | What it tests |
|------|--------------|
| `renders "No alerts yet." when alerts array is empty` | Empty state message shown for `alerts={[]}` |
| `renders "No alerts yet." when alerts prop is omitted` | Empty state shown when prop is missing entirely |

**Alert list rendering**
| Test | What it tests |
|------|--------------|
| `renders all alerts` | All three alert text bodies are visible |
| `renders severity in title (uppercase)` | CRITICAL, MEDIUM, LOW labels are shown |
| `renders anomaly score and trend` | Score and trend values appear in the card |
| `renders timestamps` | Time strings are displayed |

**ACTIVE / PAST tags**
| Test | What it tests |
|------|--------------|
| `marks the most recent alert (displayed first) as ACTIVE` | First displayed alert has the `ACTIVE` tag |
| `renders PAST tags for older alerts` | All other alerts show `PAST` tags |

**Ask agent button**
| Test | What it tests |
|------|--------------|
| `shows "Ask agent" button only for the active alert` | Exactly one button is rendered |
| `calls onGoChat when "Ask agent" button is clicked` | `onGoChat` callback is invoked on click |

**Single alert edge case**
| Test | What it tests |
|------|--------------|
| `marks the single alert as ACTIVE (not PAST)` | One alert → ACTIVE tag, no PAST tag |
