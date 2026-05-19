# SpirulinaAI — Test Suite Documentation

---

## How to run

**Backend (Python):**
```powershell
.venv\Scripts\pytest tests/ -v
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

### `test_ml_models.py` — ML Prediction Pipeline Unit Tests

Tests all three machine learning models without loading real artifacts — models and scalers are mocked so tests run fast with no GPU required.

**M1 — LSTM Anomaly Detector helpers**
| Test | What it tests |
|------|--------------|
| `test_severity_critical` | Score ≥ 0.80 returns `"critical"` |
| `test_severity_medium` | Score between 0.55–0.79 returns `"medium"` |
| `test_severity_low` | Score < 0.55 returns `"low"` |
| `test_norm_score_clamps_to_01` | Normalized score is always clamped between 0 and 1 |
| `test_norm_score_zero_range` | No division-by-zero when score_min == score_max |
| `test_trend_direction_declining` | Rising scores → `"declining"` trend |
| `test_trend_direction_recovering` | Falling scores → `"recovering"` trend |
| `test_trend_direction_stable` | Flat scores → `"stable"` trend |
| `test_trend_direction_single_value` | Single score (can't compute delta) → `"stable"` |
| `test_trend_direction_all_nan` | All NaN values → `"stable"` (no crash) |
| `test_sensor_attribution_sums_correctly` | Equal error across sensors → equal attribution values |
| `test_sensor_attribution_returns_all_columns` | Output dict has all 6 sensor keys |

**M1 — `predict_df` output validation**
| Test | What it tests |
|------|--------------|
| `test_output_columns_present` | Result DataFrame contains all expected columns |
| `test_output_length_equals_input_length` | Output has same row count as input |
| `test_is_anomaly_is_boolean` | `is_anomaly` column is boolean type |
| `test_severity_values_are_valid` | `severity` only contains `"critical"`, `"medium"`, or `"low"` |
| `test_sensor_attribution_is_valid_json` | Each `sensor_attribution` cell parses as valid JSON |
| `test_raises_on_missing_columns` | `ValueError` raised when sensor columns are absent |
| `test_raises_on_unparseable_date` | `ValueError` raised when date column has invalid values |
| `test_scores_nan_for_rows_before_window` | Rows before window_size get `NaN` anomaly score (not a crash) |

**M2 — LightGBM Turbidity Forecaster**
| Test | What it tests |
|------|--------------|
| `test_output_keys_present` | Result dict has `low`, `prediction`, `high`, `date` |
| `test_prediction_within_low_high_range` | `low ≤ prediction ≤ high` is always satisfied |
| `test_raises_when_features_empty` | `ValueError` raised when `build_features` returns empty DataFrame |

**M3 — Harvest Scheduler helpers**
| Test | What it tests |
|------|--------------|
| `test_reason_not_ready` | `"not_ready"` label produces a "not ready" message |
| `test_reason_heavy` | `"heavy"` label includes harvest percentage and "optimal" |
| `test_reason_moderate` | `"moderate"` label includes harvest percentage |
| `test_reason_light` | `"light"` label includes harvest percentage |
| `test_recommendation_all_not_ready` | All days not_ready → recommendation says "not ready" |
| `test_recommendation_best_is_today` | Best day is today → recommendation references today |
| `test_recommendation_best_is_tomorrow` | Best day is tomorrow → recommendation says "tomorrow" |
| `test_recommendation_best_is_day_after` | Best day is day+2 → recommendation says "2 days" |

**M3 — `schedule` and `_score_row`**
| Test | What it tests |
|------|--------------|
| `test_raises_when_too_few_rows` | `ValueError` raised when fewer than 6 rows provided |
| `test_schedule_output_keys` | Result dict has `today`, `tomorrow`, `day_after`, `recommendation` |
| `test_score_row_returns_expected_keys` | Row scoring returns `label`, `harvest_pct`, `confidence` |
| `test_score_row_returns_not_ready_on_nan_features` | NaN feature values → `not_ready` with 0% harvest (no crash) |

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

30 messages across 4 intent labels run through the Groq `llama-3.1-8b-instant` classifier:

- 8 × `KNOWLEDGE` — factual questions about spirulina biology
- 8 × `UPDATE` — parameter change instructions
- 7 × `HARVEST` — harvest readiness questions
- 7 × `SYSTEM` — sensor status and device queries

Reports classification accuracy %. Target: ≥ 90%.

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
| `prepends a checkmark to each tool` | Each pill displays `"✓ <tool name>"` |

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
