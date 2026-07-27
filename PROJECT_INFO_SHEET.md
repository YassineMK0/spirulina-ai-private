# PROJECT INFO SHEET — SpirulinaAI

*Compiled from the full git history, README/HANDOFF/TESTS docs, and the source
trees of `g:\Spirulina`, `G:\dataset`, `G:\models\anomaly_model`,
`g:\cpc detection`, `g:\spiruline counting\labeling`, and
`g:\counting number 2`. Sections 2 and part of 3 need your input — I can't
invent institutional details or the personal framing of the problem
statement; everything else is drawn directly from the codebase.*

---

## 1. Project name & one-line description

**SpirulinaAI** — an AI-powered assistant and monitoring platform for
industrial spirulina (*Arthrospira/Limnospira platensis*) cultivation:
a bilingual (FR/EN) RAG chatbot for cultivation questions and troubleshooting,
real-time sensor monitoring with proactive anomaly alerts, and three
machine-learning models (sensor anomaly detection, biomass/CPC estimation
from images, and contamination/species screening from microscope images).

---

## 2. Context / host — *[needs your input]*

- **Company / internship type (PFE, stage, etc.):** PFE (Projet de Fin
  d'Études), hosted at **AlgaePool** — a spirulina production operation
  (production parameters, thresholds, and the anomaly catalog used
  throughout the ML models were supplied directly by AlgaePool's own
  cultivation expert, Dominique Delobel).
- **Supervisors (academic + professional):** *[fill in]*
- **Duration / timeline:** *[fill in official dates]*. For reference, the
  git history runs from **2026-03-06** (first commit, RAG pipeline + chat
  UI) to **2026-07-26** (final UI polish pass) — about 4.5 months of visible
  development activity, in case that's useful to cross-check against your
  official start/end dates.

---

## 3. Problem statement — *[draft; adjust tone/framing to your own words]*

**Before:** Spirulina cultivation at AlgaePool scale relies on manual sensor
readings (pH, EC, dissolved oxygen, temperature, luminosity, turbidity) and
an operator's own experience to catch problems — contamination, pH crashes,
heat stress, nutrient imbalance — often after they've already affected
culture health. Diagnostic and cultivation knowledge exists but is scattered
across PDFs, manuals, and one expert's head, not something an operator can
query in the moment. There was no automated way to flag an anomalous
reading, estimate biomass/harvest readiness from a photo, or screen for
contaminating species without manual microscopy expertise.

**Why it matters:** In a live culture, several of these failure modes
(pH excursions, heater faults, contamination) can compound quickly, and
production knowledge that only exists in an expert's head doesn't scale
past that one person's availability. The project's own reference material
is explicit that the practical failure mode to avoid isn't "no alerts," it's
**alert fatigue** — a system that fires so often operators start ignoring it
(*"le pire : un système qui clignote en permanence... l'utilisateur submergé
finira par s'en détourner"* — AlgaePool expert questionnaire).

---

## 4. Objective & expected results

**What the system does when finished:**
- Answers spirulina cultivation questions (pH, temperature, nutrients,
  light, EC, harvest timing) in French and English, grounded in a curated
  document corpus.
- Diagnoses cultivation problems (yellow color, pH crash, contamination,
  slow growth, heat stress) using an agentic reasoning loop with real
  calculation tools (pH/EC correction dosing).
- Reads live sensor data over MQTT and evaluates it through a three-layer
  anomaly detector (rule engine + seasonal check + unsupervised outlier
  model) every 15 seconds.
- Proactively pushes alerts to the user (no need to ask) via Server-Sent
  Events, deduplicated by breach type/direction, with grounded LLM-generated
  explanations of the specific failure mode and one concrete action.
- Estimates biomass (via a C-phycocyanin proxy) directly from a microscope
  or flask photo.
- Screens a microscope image for contaminating microalgae species.
- Provides a full web dashboard: live sensor readings, 14-day trend charts,
  alert history, model outputs, multi-user auth with free/pro/admin tiers,
  and an admin panel.

**Concrete deliverables:**
- LangGraph-based conversational agent (FastAPI backend) with intent
  routing, RAG retrieval, and a dual-mode generator (fluent-prose vs.
  tool-calling reasoning agent).
- Hybrid (BM25 + dense) RAG pipeline over 5,300+ chunks from 20+ FR/EN
  cultivation documents, evaluated with RAGAS.
- `models/anomaly_model/` — rule engine + seasonal z-score + Local Outlier
  Factor combination model, trained on real AlgaePool sensor history.
- `models/cpc_model/` — CNN + XGBoost biomass/CPC regressor from images.
- `models/species_classifier/` — shape/texture feature + XGBoost species
  classifier for contamination detection.
- MQTT sensor ingestion + simulator covering every reachable alert scenario.
- Next.js web application (chat, dashboard, alerts, models, admin, auth).
- Automated test suites: 149+ backend pytest tests, Jest frontend tests,
  RAGAS RAG-quality evaluation, latency profiling.
- Docker/Compose deployment setup.

---

## 5. Architecture

- **Frontend stack:** Next.js 16 (App Router), React 19, React Context
  (no Redux/Zustand), Recharts for trend charts, `react-markdown` +
  `remark-gfm` for chat rendering, PWA basics (manifest, service worker).
  Tailwind is installed but styling is mostly inline objects against a
  theme-token file.
- **Backend stack:** FastAPI (Python), Uvicorn, Pydantic.
- **Database(s) / cache:** PostgreSQL (users, conversations, alerts),
  SQLite (sensor time-series store), Redis (conversation memory cache,
  optional — falls back to in-memory).
- **Agent orchestration:** LangGraph + LangChain — a graph of nodes
  (intent classification → RAG retrieval → gated branches for
  sensors/ML/reasoning → response generation → formatting) with explicit
  routing gates for low-confidence, off-domain, and memory-recall cases.
- **RAG setup:** ChromaDB vector store; embeddings documented as
  `BAAI/bge-m3` (1024-dim, multilingual) — one observed run actually loaded
  `paraphrase-multilingual-mpnet-base-v2` instead, an unresolved
  discrepancy worth confirming before citing a specific model in the
  report. Retrieval is hybrid BM25 + dense, merged via Reciprocal Rank
  Fusion, top-k=8.
- **LLM(s) used:** currently a **local** model, Ollama `qwen3:8b`, for all
  three roles (intent routing, RAG generation, reasoning agent) — chosen to
  fit an 8GB-VRAM laptop GPU and to avoid the request-quota limits of the
  API providers used earlier in the project (Groq `llama-3.1-8b-instant` /
  `llama-3.3-70b-versatile` for routing/generation, OpenRouter
  `nemotron-3-super-120b-a12b` for reasoning). The provider is
  env-var-switchable per role, so both paths still work.
- **ML models:**
  | Model | Task | Algorithm | Key metric |
  |---|---|---|---|
  | Anomaly detector (`models/anomaly_model`) | Sensor anomaly detection (pH, EC, DO, temperature, luminosity, turbidity) | 3-layer: expert rule engine + robust seasonal z-score (Temperature/Luminosité) + Local Outlier Factor on 24h rolling aggregates | LOF F1 = 0.853 (vs. Isolation Forest 0.739) on synthetic anomaly-injection benchmark, 30 trials |
  | CPC / biomass predictor (`models/cpc_model`) | Biomass estimation (C-phycocyanin concentration) from a flask/microscope photo | CNN feature encoder (frozen) → XGBoost regression | R² = 0.988 on a random train/val split (see §8 — this is a known-inflated evaluation, not the honest leave-one-day-out figure) |
  | Species classifier (`models/species_classifier`) | Contamination screening (3-way species ID) | 31 classical shape/texture features → StandardScaler → XGBoost | 97.3% accuracy on a held-out sample (matches the source paper's ~97%) |
- **CV components:** yes — two image-based models (CPC regression, species
  classification), both classical CNN-feature/hand-engineered-feature +
  gradient-boosting pipelines. **No object detection, no OCR, no
  vision-language model.** (See §9 — an earlier exploratory filament/cell
  *counting* CNN was built but is not part of the deployed product.)
- **Auth:** custom HS256 JWT (signup/login, bcrypt-hashed passwords);
  AWS Cognito RS256 verification wired in but inactive (auto-detects issuer,
  falls back to custom JWT); free/pro/admin tiers.
- **Deployment:** Docker + docker-compose (FastAPI backend + Redis, with
  persistent volumes for the vector store and model cache).
- **Testing:** pytest (backend, 149+ tests — unit, integration, live-LLM,
  API endpoint), Jest + Testing Library (frontend), RAGAS (RAG quality),
  a synthetic anomaly-injection benchmark (ML model selection), and a
  50-scenario live end-to-end conversation suite.

---

## 6. Dataset(s)

- **RAG corpus:** 20+ source documents (scientific PDFs, cultivation
  manuals, an AlgaePool reference document, a hand-written troubleshooting
  guide), French and English, chunked into ~5,300 pieces and embedded into
  ChromaDB.
- **Sensor / anomaly-detector data:** one real historical CSV,
  `iot_features_5min.csv` — **106,111 rows spanning 368 days** of AlgaePool
  production sensor readings, supplied by the company. On audit, this
  turned out to be two datasets glued together: Temperature and Luminosité
  have genuine 5-minute-resolution readings throughout, while pH/EC/DO/
  Turbidité have only **354 real daily readings**, linearly interpolated
  for the rest (flagged by `*_is_interpolated` columns) — the anomaly
  model's training code (`data.py`) was written to only ever train on the
  354 real points for those four sensors, never the interpolated filler.
  Thresholds and the anomaly catalog itself came from a structured
  questionnaire with the AlgaePool cultivation expert (Dominique Delobel),
  not from labeled anomaly examples — **no ground-truth anomaly labels
  exist anywhere in the project**, which is why the combination-model
  evaluation had to use synthetic anomaly injection instead of real
  precision/recall (see §7).
- **Separate lab-scale sensor data (`G:\dataset`):** four raw CSVs from
  small-scale Erlenmeyer flask trials (5 Mar, 9 Mar, 26 Mar, 11 Apr batches),
  parsed by `parse_real_data.py` into a 132-row `real_data.csv`. This looks
  like an earlier/parallel data-exploration exercise — worth confirming
  with your own notes whether it fed into any deployed model, since the
  deployed anomaly detector's own documentation cites only
  `iot_features_5min.csv` as its training source.
- **CPC / biomass image dataset:** the public *Exp_2_Spirulina_Image_Dataset*
  (Chong et al. 2025) — **11,520 images** across 6 culture days × 2 devices
  (iPhone/Nikon) × 2 lighting conditions × 3 batches, pooled into one model
  (the source paper trained 8 separate per-condition models; this project
  deliberately trained one pooled, device-agnostic model instead).
- **Species classifier dataset:** the same source repo's
  *Microalgae_Image_Dataset* (3 classes: *Spirulina platensis*, *Chlorella
  FSP*, *Chlamydomonas reinhardtii*); ~630 images (70/class/batch) were
  sampled to reconstruct a missing feature-normalization step, then the
  model was validated on a fresh 75-image sample.
- **Filament/cell-counting dataset (exploratory, not deployed):**
  1,050 AlgaePool culture photos (`[ALGP] Photos/`, several culture batches
  and one agricultural-medium trial) manually annotated via a custom
  point-and-click Flask tool (`count_app.py`) — each click marks one
  filament/cell, auto-saved as one JSON file per image plus a combined
  `combined_annotations.json`. Used to train/finetune a CNN counting model
  (`cnn_checkpoint.pt`, `cnn_checkpoint_finetuned.pt`), but this pipeline is
  not referenced anywhere in the deployed `g:\Spirulina` codebase — it
  appears to have been superseded by the direct CPC image-regression
  approach, which estimates biomass without needing an explicit per-cell
  count.

---

## 7. Key experiments / results

**Anomaly-detector combination-model selection** (2026-06-24,
`compare_models.py` / `model_comparison_report.md`): four unsupervised
models — Isolation Forest (original choice), Local Outlier Factor,
One-Class SVM, Elliptic Envelope — benchmarked via synthetic anomaly
injection (30 trials; ~10% of the 354 real daily records perturbed by
shifting 2 random features 3–6 standard deviations, since no real anomaly
labels exist):

| Model | Precision | Recall | F1 | F1 std |
|---|---|---|---|---|
| **Local Outlier Factor** | **0.991** | 0.749 | **0.853** | **0.022** |
| Isolation Forest | 0.815 | 0.675 | 0.739 | 0.064 |
| One-Class SVM | 0.617 | 0.484 | 0.540 | 0.081 |
| Elliptic Envelope | 0.364 | 0.302 | 0.330 | 0.039 |

LOF was chosen for production — most precise, most stable across trials,
and its neighborhood-relative comparison naturally handles the dataset's
seasonal drift (EC trends upward across the season) better than the global
methods.

**CPC/biomass model — four iterations**, each diagnosing and fixing a
shortcut-learning problem:
1. *cpc_first_model:* end-to-end CNN → SVM/XGBoost; found the CNN was
   learning "brightness/darkness" (which rises monotonically over the run)
   rather than true CPC dynamics (which peaks at day 8, then crashes) —
   pooled leave-one-day-out (LODO) R² was negative.
2. *cpc_third_model:* tried full-frame (no crop) input + a hand-computed
   `mean_saturation` feature (saturation tracks the true day-8 turnaround
   that raw brightness doesn't) — improved direction but not fully.
3. *cpc_fourth_model:* decoupled the CNN encoder from the CPC label
   entirely (pretrained as an autoencoder on reconstruction loss only),
   then fit XGBoost on the frozen features — simplified away SVM/meta-
   stacking.
4. **Deployed model** (`second and third/biomass_cpc_model_random_split.pt`,
   used by `models/cpc_model/predictor.py`): random-split evaluation gives
   **R² = 0.988, MAE ≈ 0.0065 mg/mL** — see §8 for why this number should be
   quoted carefully in the report.

**Species classifier:** reconstructed a missing first-stage feature-
normalization step (the source repo's own scaler was a near-identity
transform on already-normalized features, not reproducible from a single
inference image) — validated at **97.3% accuracy** on a fresh 75-image
sample, matching the source paper's reported ~97%.

**RAG quality (RAGAS, 30 questions, `llama-3.3-70b-versatile` as judge,
hybrid retrieval top-k=8):**

| Category | Relevance | Faithfulness | Recall |
|---|---|---|---|
| Factual | 0.730 | 0.930 | 0.700 |
| Troubleshooting | 1.000 | 0.990 | 0.867 |
| Operational | 0.900 | 0.883 | 0.733 |
| **Overall** | **0.873** | **0.942** | **0.767** |

All above target thresholds (0.80 / 0.85 / 0.70).

**Conversational pipeline:** 50 end-to-end scenario tests (knowledge,
multi-turn, troubleshooting, harvest, no-container), **50/50 pass**,
90.7% average score. Intent-classification accuracy: ~90% on the original
Groq router, ~97% measured on the current local `qwen3:8b` model.

**LLM provider migration:** moved all three LLM roles from
Groq/OpenRouter APIs to a local Ollama model, to remove dependence on
free-tier token quotas. This surfaced and fixed two real bugs: the local
model's "thinking mode" was silently consuming the entire token budget on
`<think>` reasoning before producing an answer (intent router returning
empty/`UNKNOWN` with no error), and the reasoning-agent LLM getter had been
hardcoded to one provider with no fallback — the likely real cause of
alerts previously showing generic, unexplained text.

---

## 8. Known limitations / rough edges

- **CPC model evaluation caveat:** the deployed checkpoint's headline
  R² = 0.988 comes from a **random** train/val split. The project's own
  analysis (`ARCHITECTURE_CHANGES.md`) shows this is likely inflated by
  near-duplicate frames of the same physical flask leaking across
  train/val — an early honest **grouped/leave-one-day-out** evaluation on
  the same kind of data dropped to R² ≈ 0.4 (one fold as low as -1.3). This
  should be stated carefully in the report rather than quoting 0.988 as a
  generalization estimate.
- **RAG embedding-model discrepancy:** documentation says `BAAI/bge-m3`;
  one observed run actually loaded a different multilingual model
  (`paraphrase-multilingual-mpnet-base-v2`). Not yet reconciled.
- **Historical sensor data isn't from an optimally-run culture:** the rule
  engine fires on almost every one of the 354 real days (e.g. Temperature
  never once reached the expert's optimal 34–39°C range in 368 days) —
  deploying the "optimal-range" warnings as-is would alert constantly. The
  fix (demote sub-optimal-but-not-dangerous bands to info-only, keep
  absolute danger thresholds critical) is proposed but explicitly flagged
  as **not yet applied** in the model's own documentation.
- **No real anomaly ground truth exists** anywhere in the project — the
  expert was explicit that there isn't enough history to validate against.
  Several specific thresholds remain open questions from the expert
  himself: no OD680↔Secchi-disk conversion, no validated abnormal-turbidity
  drop rate, no data on whether low nighttime DO is truly abnormal, no
  validated cross-sensor correlation pairs specific to this site, no
  alert-priority/response-time table.
- **Filament-counting CNN experiment** (1,050 hand-labeled images) was
  built but never integrated into the deployed product — superseded by the
  direct CPC regression approach.
- **The lab-scale `G:\dataset` CSVs** (132 parsed rows) don't appear to
  feed any deployed model — worth confirming whether this was meant to be
  used and isn't yet, or was an exploration that was abandoned.
- **Backend:** duplicate MQTT simulator logic in two files; the SSE alerts
  endpoint passes the JWT as a URL query parameter (browser/EventSource
  limitation, but leaks the token into logs); the daily ML prediction runs
  twice independently (dashboard endpoint + monitor loop) with no shared
  cache; the free-tier 3-messages/day cap isn't enforced when running
  without a configured Postgres database (in-memory fallback).
- **Frontend:** two legacy components (`FreeTier.jsx`, `ProShell.jsx`)
  appear dead but were never removed; no toast/error-notification system
  (failed calls mostly fail silently); the active container ID is
  hardcoded in the UI despite the backend being fully multi-container-
  aware; sensor "optimal range" bands are hardcoded in the dashboard
  instead of coming from the backend's single source of truth; fixed
  polling intervals with no retry/backoff on failure; no pagination/search
  for long conversation histories.
- **Wired but inactive:** AWS Cognito auth (needs AWS credentials/pool),
  Sentry error tracking and Logstash log shipping (need their respective
  endpoints configured) — all three are fully implemented, just not turned
  on.

---

## 9. What NOT to mention

Confirmed by checking every model actually used in this project against
the source code and training scripts — **none of the following apply**,
so they shouldn't appear in the report:

- **No object detection framework** (YOLO or otherwise) anywhere in the
  pipeline. Both image-based models (CPC estimation, species
  classification) work on the whole image via a CNN feature
  extractor / hand-engineered features feeding a gradient-boosted tree
  model (XGBoost) — not a detector, not a segmentation network.
- **No OCR.** Nothing in this project reads text from images.
- **No LayoutLM or any document-layout model.** The RAG pipeline parses
  PDFs for their text content only (PyMuPDF), with no layout/structure
  modeling.
- **No vision-language model (VLM).** Image inputs (CPC, species
  classification) go through classical CV/CNN feature pipelines only, not
  a multimodal LLM.
- **No KiCad or any electronics-design tooling** — this is a pure
  software project; sensor hardware (pH probe, Atlas Scientific EZO-EC/DO
  kits, DS18B20, DFRobot lux sensor, EVAL-CN0409-ARDZ turbidity sensor) is
  referenced only as the data source the ingestion pipeline was designed
  around, not something designed in this project.
- **No deployed filament/cell-counting model** — that CNN was trained
  experimentally (see §6/§8) but is not part of the shipped product; don't
  describe cell-counting as one of the three deployed ML models. The three
  deployed models are: sensor anomaly detector, CPC/biomass regressor,
  species classifier.

---

*If anything above conflicts with what you remember building, trust your
own memory of intent over this document — it's reconstructed from code and
commit history, which captures what was built and why it changed, not
always the full reasoning in the moment.*
