# SpirulinaAI — Project Handoff

A chatbot + dashboard for monitoring spirulina algae cultivation containers (sensors: pH, EC, DO, temperature, luminosity, turbidity), built for AlgaePool production conditions (expert: Dominique Delobel, June 2026).

## Architecture Overview

```
Frontend (Next.js 16, React 19)  →  FastAPI backend  →  LangGraph agent
                                          │
                          ┌───────────────┼───────────────┐
                     PostgreSQL      ChromaDB (RAG)    MQTT broker
                  (users/convos/      bge-m3 embed    (test.mosquitto.org)
                   alerts)            + BM25 hybrid         │
                                                    agent/sensors.py
                                                    agent/monitor.py
                                                    (every 15s, threaded
                                                     Groq alert generation)
```

**Backend**: FastAPI (`api/main.py`), LangGraph pipeline (`agent/graph.py`), Groq LLM (router: llama-3.1-8b-instant, generator/reasoning: llama-3.3-70b-versatile), ChromaDB + bge-m3 + BM25 hybrid RAG, 3 ML models (M1 IsolationForest anomaly detection, M2 LightGBM turbidity forecast, M3 LightGBM harvest scheduler), MQTT sensor ingestion, SSE proactive alerts, JWT auth with optional AWS Cognito support, free/pro/admin tiers.

**Frontend**: Next.js App Router, React Context (no Redux), inline-styled components with a centralized theme token system (`lib/theme.js`), fetch-based API client (`lib/api.js`).

---

## Backend — Current State

### Auth (`api/auth.py`, `api/cognito.py`)
- Custom HS256 JWT (signup/login) — works today, no AWS dependency
- Cognito RS256 verification wired in but **inactive** (env vars blank) — auto-detects token issuer, falls back to custom JWT transparently. Activate by filling `COGNITO_REGION`/`COGNITO_USER_POOL_ID`/`COGNITO_APP_CLIENT_ID` in `.env`
- Free tier: 3 messages/day, resets at midnight UTC (`data/users.py: count_messages` filters `created_at >= CURRENT_DATE`)
- First user ever created becomes `admin` automatically

### ML Models
- **M1** (`api/predict_isolationforest.py`): sklearn Pipeline (scaler + IsolationForest), replaced an LSTM autoencoder. Threshold = 95th percentile of normal validation scores (0.7156). Two detection layers: statistical (`norm_ml >= threshold`) OR expert rule violation (`rule_score >= 0.80`). EC auto-converts µS/cm → mS/cm when median > 100. Confirmed detections: Chlorella invasion (pH < 8.5), EC dilution (< 12 mS/cm), heater fault (temp > 41°C), pH alkalinity overrun (> 11.5)
- **M2** (`api/predict_lgbm.py`): turbidity forecast (low/prediction/high band)
- **M3** (`api/predict_lgbm_harvest.py`): harvest % recommendation, today + tomorrow

### Monitor (`agent/monitor.py`)
- Runs every 15s via APScheduler (`max_instances=3`)
- Checks `_active_sessions` (populated by `/chat` or `/alerts` SSE connection with `container_id`)
- Threshold rules + M1 ML prediction run synchronously (fast); **Groq alert-text generation runs in a background thread** so slow LLM calls never block the next tick
- Alert prompt includes actual sensor values + ML sensor attribution, asks Groq to name the specific failure mode and give one concrete action

### Observability (`api/logging_setup.py`)
- Sentry + python-logstash-async wired in, both **inactive** unless `SENTRY_DSN` / `LOGSTASH_HOST` are set in `.env`
- All `print()` in `main.py`, `monitor.py`, `sensors.py` converted to `logging` calls

### MQTT (`agent/sensors.py`, `mqtt simulator/sensors.py`)
- Broker: `test.mosquitto.org:1883` (HiveMQ public broker stopped responding, switched away from it)
- paho-mqtt 2.x compatible (version-aware callback signatures)
- Simulator (`mqtt simulator/sensors.py`) sends the 4 confirmed M1 detection scenarios with correct AlgaePool-scale values (EC in mS/cm equivalents, not generic hobbyist ranges)

### Known rough edges (backend)
- `agent/sensors.py` has a duplicate, slightly different `__main__` simulator block — redundant with `mqtt simulator/sensors.py`, consider deleting one
- SSE alert endpoint passes JWT as a query param (`?token=...`) instead of header, because `EventSource` doesn't support custom headers — fine for now but visible in server logs/browser history
- `/models/{container_id}` and monitor's `_run_ml_prediction` both call `predict_df` independently — could share a cache to avoid double inference every 15s
- In-memory user store fallback (no `DATABASE_URL`) doesn't enforce the free-tier message limit (`count_messages` always returns 0)

---

## Frontend — Current State

**Stack**: Next.js 16 (App Router), React 19, Context API (no Redux/Zustand), Tailwind CSS 4 (mostly unused — components use inline style objects against `theme.js` tokens), `react-markdown` + `remark-gfm` for chat rendering.

**Structure**: `spirulina-ui/components/` — `SpirulinaApp.jsx` (tier-based router) → `chat/AgentChat.jsx`, `dashboard/DashboardPage.jsx`, `alerts/AlertsPage.jsx`, `models/ModelsPage.jsx`, `admin/AdminPage.jsx`, `auth/LoginPage.jsx`. All API calls centralized in `lib/api.js`.

**Auth flow**: JWT in localStorage (`spirulina-token`), validated via `/auth/me` on load, attached as `Authorization: Bearer` header on every request except SSE (query param).

**Real-time**: SSE for alerts (`connectAlerts`), polling for sensors (10s) and model outputs (15s, `cache: "no-store"`).

### Known rough edges (frontend)
1. **Dead/legacy code**: `FreeTier.jsx` and `ProShell.jsx` appear superseded by `SpirulinaApp.jsx` but still exist with duplicated polling/alert logic — should be deleted or reconciled
2. **No error UI**: failed API calls mostly fail silently (return empty arrays); no toast/banner system
3. **Hardcoded values**: `CONTAINER_ID = "container-01"` hardcoded in `SpirulinaApp.jsx` — no multi-container support in the UI despite the backend being container-aware; sensor optimal ranges hardcoded in `DashboardPage.jsx` instead of pulling from the backend's AlgaePool thresholds
4. **No loading skeletons** — dashboard/models pages show plain text "Loading…" 
5. **No conversation search, export, or pagination** — full history loads at once
6. **Inconsistent theme usage** — `FreeTier.jsx` uses hardcoded hex colors instead of `useTheme()` tokens
7. **No responsive/mobile testing** — desktop-first, fixed-width sidebar, no breakpoints observed
8. **Fixed poll intervals** — 10s/15s not configurable, no backoff on error, no exponential retry on SSE disconnect

---

## Suggested Next Steps (priority order)

1. **Multi-container support in UI** — backend already keys everything by `container_id`; frontend hardcodes one. Add a container picker/switcher.
2. **Error notification system** — toast/banner for failed API calls, SSE disconnects, 429 rate limits (currently only chat 429 surfaces to the user).
3. **Reconcile or delete `FreeTier.jsx` / `ProShell.jsx`** — confirm with the team whether they're dead code before removing.
4. **Pull sensor optimal ranges from the backend** instead of hardcoding in `DashboardPage.jsx` — single source of truth matches the AlgaePool expert thresholds already in `models/feature_engineering/feature_engineering_isolation_forest.py`.
5. **Activate Cognito and/or Sentry/Logstash** once AWS access is available — both are fully wired, just need env vars.
6. **Loading skeletons + retry/backoff** for sensor and model polling.
7. **Conversation pagination/search** for users with long chat histories.

This file is meant as a working reference — update it as the above items get done or priorities shift.
