# SpirulinaAI — Project Report

*A chronological and architectural account of the project, from the first commit (2026-03-06) to the current state (2026-07-26).*

---

## 1. What the project is

SpirulinaAI is an intelligent assistant + monitoring dashboard for **spirulina algae cultivation**, built around real production parameters supplied by an industry expert (Dominique Delobel, AlgaePool, June 2026). It combines:

- A **conversational agent** (chat) that answers cultivation questions, diagnoses problems, and recommends harvest timing, in French and English.
- **Live sensor monitoring** (pH, EC, dissolved oxygen, temperature, luminosity, turbidity) ingested over MQTT.
- **Three machine-learning models** that read those sensors: an anomaly detector, a CPC (phycocyanin/biomass) image predictor, and a microalgae species classifier for contamination detection.
- A **proactive alerting system** that watches containers in the background and pushes alerts to the UI without the user asking.
- A full **Next.js web app** (auth, dashboard, chat, alerts, admin) sitting on top of a FastAPI backend.

It was built solo, iteratively, over roughly 4.5 months, with AI pair-programming (Claude) credited as co-author on several commits.

---

## 2. Timeline

| Date | Commit(s) | Milestone |
|---|---|---|
| 2026-03-06 | `c492770` — *SpirulinaAI v1* | First working version: RAG pipeline + single-page `chat.html` UI. Ingested ~15 PDFs/guides (French + English spirulina literature) into ChromaDB. Basic LangGraph agent: classify intent → retrieve → generate. |
| 2026-03-24 | `27684c6` — *SpirulinaAI v2* | Dual-LLM pipeline added (Groq Llama 3.3 70B for RAG generation + OpenRouter Nemotron 120B for reasoning). Proactive monitoring via APScheduler + SSE. 6 named fake test containers for anomaly scenarios. Edge-case handling (ambiguous intent, off-domain, no container, long queries, memory recall). 50-scenario conversation test suite (50/50 pass). Switched embeddings to BGE-M3 (1024-dim, multilingual) with hybrid BM25+dense RRF retrieval. Removed early scaffolding (`streamlit_app.py`, `ml/`, old notebooks). |
| 2026-04-15 | `c610bf8` | First real ML modeling push: `api/predict_anomaly.py`, hand-built `data/generate_data.py` + `data/features.py` synthetic training data (12k train / 3k test rows), a `docs/phase_a_technical_note.md` write-up, RAGAS eval results file. Added a real `algaepool.pdf` reference doc. |
| 2026-04-26 | `0794e57` | Dockerization begins: `Dockerfile`, `.dockerignore`, `docker-compose.yml` (backend + Redis, ChromaDB volume, model cache volume). The old Vite/React frontend scaffold under `spirulina-ui/` (index.html, App.css, eslint config) was removed in preparation for a rebuild. |
| 2026-05-12 | `616c58d` | Frontend rebuilt from scratch on **Next.js** (App Router). Backend gained `api/predict_lgbm.py`, `api/predict_lgbm_harvest.py`, `api/predict_lstm.py` — the first "M1/M2/M3" ML trio (LSTM anomaly autoencoder, LightGBM turbidity forecaster, LightGBM harvest scheduler). Added `data/store.py` (SQLite-backed sensor store) — synthetic CSV datasets and `generate_data.py` removed now that a real sensor pipeline existed. Old flat `chat.html` removed. |
| 2026-05-19 | `20a485e` | SEO/PWA polish on the frontend (manifest, robots.txt, sitemap, service worker), first Jest test files (`atoms`, `Bubble`, `AlertsPage`, `api`). `TESTS.md` written. First backend API integration tests (`test_api_endpoints.py`). |
| 2026-06-03 | `a7e389f` | Chat UX overhaul: conversation sidebar, markdown rendering, theming system (`theme.js`, `ThemeContext`), `agent/tools.py` (ReAct tool-calling for the reasoning agent), `data/conversations.py` (persisted multi-conversation history). |
| 2026-06-09 | `ab9e08c` | **Auth & multi-tenancy**: `api/auth.py`, `api/admin.py`, `data/users.py`, `data/alerts.py`, JWT-based login/signup, admin dashboard, free/pro/admin tiers. |
| 2026-06-10 | `8be0f00` + `9ab4268` | `api/predict_isolationforest.py` replaces the LSTM autoencoder as M1 (sklearn `Pipeline`: scaler + `IsolationForest`). `feature_engineering_isolation_forest.py` encodes AlgaePool-scale expert thresholds. MQTT simulator rewritten to emit AlgaePool-realistic values. `test_crash_detection.py` added. `.claude/` removed from git tracking. |
| 2026-06-29 | `46a4531` / `9580944` — *Wire M1 anomaly detector (rules+LOF)* | Major ML rewrite: LSTM/LightGBM trio (M1/M2/M3) **deleted entirely**, replaced by `models/anomaly_model/` — a rule engine (`rules.py`) + seasonal residual z-score check (`seasonal.py`) + a Local Outlier Factor "combination model" scored once/day against 24h rolling history (`detector.py`). Also: Husky git hooks (pre-commit/pre-push), `api/cognito.py` (AWS Cognito RS256 JWT support, wired but inactive), `api/logging_setup.py` (Sentry + Logstash, wired but inactive), `HANDOFF.md` written. |
| 2026-07-14 | `a02dfc7` — *CPC hybrid model* | Second ML model added: `models/cpc_model/predictor.py` — a CNN feature extractor + XGBoost regressor predicting C-phycocyanin (biomass proxy) concentration directly from microscope images (trained on ~11,520 images). Wired into `ModelsPage.jsx` and a new `/cpc/predict` endpoint. |
| 2026-07-22 | `2c94d1c` — *Final Product* | Third ML model added: `models/species_classifier/` — 31 shape/texture features → StandardScaler → XGBoost, classifying microscope images as *Spirulina platensis* vs. two contaminant species (~97% accuracy), used as a contamination signal. Also: switched all three LLM roles from Groq/OpenRouter to a **local Ollama model (`qwen3:8b`)**, added `test_local_llm.py`, fixed a `<think>`-tag/thinking-mode bug that was silently breaking intent classification and alert generation, and removed the rigid "Situation/Analysis/Action Steps" template from agent responses in favor of natural markdown (see project memory `local_llm_ollama.md` and `response_style_preference.md` for the full incident detail). |
| 2026-07-24 | `f07a804` + `e4d9d56` — *Final Product* | Dashboard gained 14-day Recharts trend charts per sensor (`GET /sensors/{id}/history`). Alerts page reorganized: day-grouping, severity filter chips, "ACTIVE"→"LATEST" rename. Fixed alert deduplication so a pH crash and a pH spike (same rule label, opposite direction) no longer collapse into one entry — added a direction-aware breach signature threaded through monitor → DB → SSE → frontend. Fixed the alert-text LLM fabricating chemistry explanations for non-chemistry (equipment/connectivity) breaches. Expanded the MQTT simulator to reach every alert source combination. Fixed a Husky pre-commit bug where paths with spaces (`mqtt simulator/sensors.py`) broke `xargs`. |
| 2026-07-26 | `c615fcf` — *Final Product* | Final UI polish pass across alerts, chat, dashboard, and models pages; alert test suite updated to match. |

---

## 3. Current architecture

```
Frontend (Next.js 16, React 19)  ->  FastAPI backend  ->  LangGraph agent
                                          |
                          +---------------+---------------+
                     PostgreSQL      ChromaDB (RAG)    MQTT broker
                  (users/convos/   bge-m3 / mpnet     (test.mosquitto.org)
                   alerts, SQLite   embed + BM25            |
                   sensor store)      hybrid          agent/sensors.py
                                                       agent/monitor.py
                                                     (every 15s, threaded
                                                      alert-text generation)
```

### 3.1 Conversational pipeline (LangGraph, `agent/graph.py`)

```
check_container -> classify_intent -> _route_after_classify
                                          |-- low confidence  -> request_clarification -> END
                                          |-- OFF_DOMAIN      -> reject_off_domain      -> END
                                          |-- MEMORY_RECALL   -> recall_memory          -> END
                                          +-- else            -> retrieve_rag -> _post_rag_gate
                                                                       |
                                                        has_container ----+---- no container
                                                              |                     |
                                                       run_ml_models         reasoning_agent
                                                              |              or generate_response
                                                       read_sensors
                                                              |
                                                     _post_sensors_gate
                                                  |-----------------------|
                                            HARVEST/SYSTEM          KNOWLEDGE/UPDATE
                                                  |                       |
                                            reasoning_agent          generate_response
                                                  |                       |
                                            format_response -> END
```

Intent labels: `KNOWLEDGE`, `UPDATE`, `HARVEST`, `SYSTEM`, `OFF_DOMAIN`, `MEMORY_RECALL`, plus `UNKNOWN` fallback below a 0.7 confidence threshold. The reasoning agent path (HARVEST/SYSTEM) is a ReAct tool-calling loop with tools defined in `agent/tools.py`: `calculate_ph_correction`, `calculate_ec_correction`, `diagnose_culture_symptom`, `format_action_plan`, `get_recent_alerts`.

### 3.2 LLM stack — evolution

| Role | v1/v2 (through 2026-06) | Current (since 2026-07-22) |
|---|---|---|
| Intent router | Groq `llama-3.1-8b-instant` | Local Ollama `qwen3:8b` |
| RAG generator | Groq `llama-3.3-70b-versatile` | Local Ollama `qwen3:8b` |
| Reasoning agent | OpenRouter `nemotron-3-super-120b-a12b:free` | Local Ollama `qwen3:8b` |

All three roles now branch on a `*_MODEL_PROVIDER` env var (`INTENT_MODEL_PROVIDER`, `GENERATOR_MODEL_PROVIDER`, `REASONING_MODEL_PROVIDER`), so the old Groq/OpenRouter path still exists and can be re-enabled by flipping the env var back — the values are left commented next to the active ones. The switch to local inference was made to avoid Groq's daily token-quota exhaustion; the model (`qwen3:8b`) was picked to fit an 8GB-VRAM laptop GPU. Getting it working surfaced two real bugs: qwen3's "thinking" mode was silently burning the whole token budget on `<think>` reasoning before ever emitting an answer (fixed with `reasoning=False` on every `ChatOllama` call site plus defensive `<think>` stripping), and the reasoning-agent LLM getter had been hardcoded to OpenRouter with no fallback, which was the real cause of alerts previously showing generic "take corrective action" text.

### 3.3 RAG pipeline

- **Vector store:** ChromaDB at `data/processed/chroma/`, ~5,300+ chunks from 20+ documents (French + English spirulina cultivation literature, troubleshooting guides, AlgaePool reference PDF).
- **Embeddings:** documented as `BAAI/bge-m3` (1024-dim, multilingual); one observed run actually loaded `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` instead — this discrepancy is flagged but not yet resolved (see project memory).
- **Retrieval:** hybrid BM25 + dense vector search merged with Reciprocal Rank Fusion (RRF), top-k=8. BM25 index is built once per `(topic, doc_type)` filter and cached.
- **Generation:** temperature=0, explicit grounding instructions in the prompt template.
- **Evaluated quality (RAGAS, 30 questions, `llama-3.3-70b-versatile` as judge):** relevance 0.873, faithfulness 0.942, recall 0.767 — all above target thresholds (0.80 / 0.85 / 0.70).

### 3.4 ML models — evolution and current state

The ML side went through a full rewrite mid-project. The original trio (M1 LSTM autoencoder → later IsolationForest, M2 LightGBM turbidity forecast, M3 LightGBM harvest scheduler) was deleted on 2026-06-29 in favor of a lighter, more interpretable **anomaly-only** system, and two independent image-based models were added afterward.

**`models/anomaly_model/` — sensor anomaly detector (current M1)**
- `rules.py` — an expert rule table (pH, EC, dissolved oxygen, temperature, luminosity, rate-of-change) directly encoding AlgaePool production thresholds; each rule returns a severity 0–3.
- `seasonal.py` — robust z-score of Temperature/Luminosite against an hour-of-day median/MAD baseline (`seasonal_baseline.json`), catches drift the static rules miss.
- `detector.py` (`AnomalyDetector`) — combines rule findings, the seasonal check, and a Local Outlier Factor "combination model" (`combination_model.joblib`) scored once daily against a container's rolling 24h feature vector (12 features: 24h min/max/mean of Temperature and Luminosite, current sparse-sensor values and day-over-day diffs). Overall severity is the max across all three layers. Confirmed detections include Chlorella invasion (pH < 8.5), EC dilution (< 12 mS/cm), heater fault (temp > 41°C), and pH alkalinity overrun (> 11.5).
- Wired into `agent/monitor.py`'s 15-second APScheduler loop; the 24h combination check runs as a daily cron via the same scheduler, with a debug endpoint (`POST /debug/run-combination-check/{container_id}`) to trigger it on demand for testing.

**`models/cpc_model/` — C-phycocyanin / biomass predictor (added 2026-07-14)**
- CNN encoder (5-layer conv trunk) → XGBoost regressor, trained on ~11,520 microscope images across 6 days of culture, pooled across conditions (Chong et al. 2025 dataset).
- Predicts biomass-proxy CPC concentration (mg/mL, validated range 0.076–0.446, R²=0.988 on a random split) directly from an uploaded image via `POST /cpc/predict`.

**`models/species_classifier/` — contamination detector (added 2026-07-22)**
- 31 classical shape/texture features → StandardScaler → XGBoost, classifying a microscope image as `Spirulina_Platensis`, `Chlorella_FSP`, or `Chlamydomonas_Reinhardtii` (source model from Chong et al. 2025, ~97% reported accuracy, independently re-validated at 97.3% on a fresh sample).
- A non-`Spirulina_Platensis` prediction is treated as a contamination signal. Required reconstructing a missing first-stage feature-normalization step (`raw_feature_stats.joblib`, `calibrate.py`) because the source repo's own scaler wasn't reproducible from a single inference image.
- Exposed via `POST /species/predict`.

### 3.5 Sensor ingestion & proactive monitoring

- `agent/sensors.py` subscribes to an MQTT broker (`test.mosquitto.org:1883` — switched to this after the previously-used HiveMQ public broker stopped responding) for live pH/EC/DO/temperature/luminosity/turbidity readings, with an in-memory cache and a SQLite fallback (`data/store.py`, `data/processed/sensors.db`).
- `mqtt simulator/sensors.py` is the development/test data source: it can emit named test scenarios (healthy, harvest-ready, pH crash, heat stress, high EC, multi-anomaly, rotating) and, as of 2026-07-24, every reachable alert-source combination (rule-only, rule+model, model-24h, across each sensor channel) plus `--backfill-24h` / `--normal` / `--clear-container` flags for exercising the combination model specifically.
- `agent/monitor.py` runs every 15 seconds (APScheduler, `max_instances=3`), checking all active chat/SSE sessions' containers against thresholds + the M1 detector. Threshold and ML scoring run synchronously (fast); Groq/Ollama alert-**text** generation runs in a background thread so a slow LLM call never blocks the next tick. Alerts dedupe on a direction-aware breach signature (not on the generated text) so repeat identical breaches collapse but a reversal (e.g. pH crash → pH spike) does not.
- Alerts are pushed to the frontend over Server-Sent Events (`GET /alerts/{user_id}`), with history persisted (`data/alerts.py`, `GET /alerts/{user_id}/history`).

### 3.6 Auth, tiers, and observability

- Custom HS256 JWT signup/login (`api/auth.py`) works standalone with no AWS dependency; the first user ever created becomes `admin` automatically.
- AWS Cognito RS256 verification is wired in (`api/cognito.py`) but inactive — it auto-detects token issuer and falls back to the custom JWT transparently; activating it just requires filling in `COGNITO_REGION` / `COGNITO_USER_POOL_ID` / `COGNITO_APP_CLIENT_ID`.
- Free / Pro / Admin tiers exist; free tier is capped at 3 messages/day (resets at UTC midnight) when a Postgres `DATABASE_URL` is configured — the in-memory fallback store does not currently enforce this limit.
- Sentry + `python-logstash-async` are wired in (`api/logging_setup.py`) but inactive until `SENTRY_DSN` / `LOGSTASH_HOST` are set; all backend `print()` calls were converted to structured `logging` calls.

### 3.7 Frontend

Next.js 16 (App Router) + React 19, no Redux/Zustand — plain React Context for auth (`AuthContext`) and theme (`ThemeContext`). Styling is inline `style` objects against a centralized token file (`lib/theme.js`); Tailwind is installed but mostly unused. All backend calls are centralized in `lib/api.js`.

Pages/components: `SpirulinaApp.jsx` (tier-based router) → `chat/AgentChat.jsx` (chat UI, markdown rendering via `react-markdown`+`remark-gfm`), `dashboard/DashboardPage.jsx` (live sensor readings + `TrendCharts.jsx`, 14-day Recharts history), `alerts/AlertsPage.jsx` (day-grouped, severity-filterable alert feed with SSE live updates), `models/ModelsPage.jsx` (anomaly detector output + CPC/species image upload+predict UI), `admin/AdminPage.jsx` (user management), `auth/LoginPage.jsx`. A PWA layer was added early (manifest, service worker, robots/sitemap, SEO notes in `spirulina-ui/SEO_GEO.md`).

Two older components, `FreeTier.jsx` and `ProShell.jsx`, are known dead/legacy code superseded by `SpirulinaApp.jsx` but were never deleted.

### 3.8 Deployment

- `Dockerfile` + `docker-compose.yml`: FastAPI backend container + Redis (conversation memory), with named volumes for the ChromaDB persistence directory and the HF/Torch model cache.
- Husky git hooks (`pre-commit`, `pre-push`) run linting/tests before commits/pushes; the pre-commit hook was fixed on 2026-07-24 after it was found to mis-split staged file paths containing spaces (e.g. `mqtt simulator/sensors.py`).

---

## 4. Testing

**Backend (`tests/`, pytest, 149+ tests as of 2026-07-22):**
- `test_anomaly_model.py`, `test_monitor_combination.py` — unit + integration tests for the rules/seasonal/LOF anomaly detector and its 24h-cron wiring against a real SQLite-backed store.
- `test_cpc_model.py` — CPC predictor tests.
- `test_local_llm.py` — live integration tests against a running Ollama server for all three LLM roles (auto-skips, doesn't fail, if Ollama isn't reachable); includes a regression test for the `<think>`-mode empty-response bug.
- `test_api_endpoints.py` — FastAPI `TestClient` coverage of every HTTP endpoint with the LangGraph pipeline, memory, sensors, and models all mocked.
- `test_nodes_unit.py` — every LangGraph node function in isolation.
- `test_conversations.py` — 50 end-to-end scenarios (10 knowledge, 10 multi-turn, 10 troubleshooting, 10 harvest, 10 no-container) run live against the LLM, scored 3 points each (intent match, non-empty response, expected keyword); last recorded result 50/50 pass, 90.7% average score.
- `test_intent_router.py` — 30-message intent-classification accuracy check; ~90% on the original Groq router, ~97% measured on the current local `qwen3:8b`.
- `test_retrieval.py` — hybrid retrieval quality across 5 query categories including a French-language check.
- `ragas_eval.py` — 20-question RAGAS evaluation (see §3.3 results).
- `latency_profile.py` — per-stage pipeline timing, target < 3s end-to-end.

**Frontend (`spirulina-ui/__tests__/`, Jest + Testing Library):** `atoms.test.jsx` (6 primitive components), `api.test.js` (all 6 `lib/api.js` functions, fetch/EventSource mocked), `Bubble.test.jsx` (chat bubble across alert/user/agent roles and content types including diagnosis and harvest cards), `AlertsPage.test.jsx` (empty state, rendering, LATEST/PAST tagging, severity filters, day grouping).

---

## 5. Known rough edges (as of the last handoff note, 2026-06-29 / still relevant)

**Backend**
- `agent/sensors.py` still has a duplicate `__main__` simulator block redundant with `mqtt simulator/sensors.py`.
- The SSE alerts endpoint takes the JWT as a query param (`?token=...`) because `EventSource` can't send custom headers — works, but leaks the token into logs/browser history.
- `/models/{container_id}` and the monitor's internal ML prediction both call `predict_df` independently every 15s — no shared cache.
- The in-memory user-store fallback (no `DATABASE_URL`) doesn't enforce the free-tier 3-messages/day limit.
- The RAG embedding-model discrepancy (documented `bge-m3` vs. an observed runtime load of `paraphrase-multilingual-mpnet-base-v2`) has not been reconciled.

**Frontend**
- `FreeTier.jsx` / `ProShell.jsx` are dead code, not yet removed.
- No toast/error-banner system — failed API calls mostly fail silently.
- `CONTAINER_ID` is hardcoded (`"container-01"`) in `SpirulinaApp.jsx` despite the backend being fully multi-container-aware; sensor optimal ranges are hardcoded in `DashboardPage.jsx` instead of coming from the backend's AlgaePool thresholds.
- No loading skeletons, no conversation search/export/pagination, fixed (non-configurable) poll intervals with no retry/backoff.

---

## 6. Tech stack summary

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph, LangChain |
| LLM inference | Ollama (local, `qwen3:8b`) — previously Groq + OpenRouter |
| Vector store | ChromaDB, sentence-transformers embeddings, rank-bm25 hybrid retrieval |
| ML models | scikit-learn (IsolationForest/LOF), XGBoost, PyTorch (CNN), OpenCV/scikit-image |
| Backend API | FastAPI, Pydantic, Uvicorn |
| Data persistence | PostgreSQL (users/conversations/alerts), SQLite (sensor store), Redis (conversation memory cache) |
| Sensor ingestion | paho-mqtt (MQTT), APScheduler |
| Auth | Custom HS256 JWT + bcrypt; AWS Cognito RS256 wired but inactive |
| Observability | Python `logging`; Sentry + Logstash wired but inactive |
| Frontend | Next.js 16 (App Router), React 19, React Context, Recharts, react-markdown |
| Testing | pytest (backend), Jest + Testing Library (frontend), RAGAS (RAG quality) |
| CI hygiene | Husky pre-commit/pre-push hooks |
| Deployment | Docker + docker-compose (backend + Redis) |

---

*Compiled from the full git history (`c492770` → `c615fcf`, 2026-03-06 to 2026-07-26), `README.md`, `HANDOFF.md`, `TESTS.md`, and the current source tree.*
