# tests/test_conversations.py

## Purpose
50-scenario end-to-end test suite covering all major conversation flows. Mocks the intent router LLM to avoid API calls; all other nodes (RAG, generators, formatters) run for real.

## Scoring
Each scenario scores 3 points:
- **+1** correct intent routed
- **+1** response not empty
- **+1** response contains expected content keywords

A scenario PASSES if score >= 2/3. Final score: 136/150 (90.7%) — all 50 pass.

## Sections

### A. Pure Knowledge Questions (10 scenarios — A01-A10)
General cultivation questions: pH, temperature, light, nutrients, OD680, protein content, EC, reproduction, species differences, greetings.

### B. Multi-Turn Dialogs (10 scenarios — B01-B10)
Follow-up questions, pronoun resolution, context switches, memory recall mid-conversation, thank-you + new question, three-turn troubleshooting flows.

### C. Troubleshooting Flows (10 scenarios — C01-C10)
Specific problems: pH drop, yellow color, white foam, bad odor, slow growth, green algae contamination, high EC, heat wave, culture crash, unusual bubbles.

### D. Harvest Timing (10 scenarios — D01-D10)
Harvest decisions at various OD680 levels, partial vs full harvest, frequency, best time of day, method, drying, refilling, yield calculation, French-language question.

### E. No Container - RAG-Only Mode (10 scenarios — E01-E10)
Confirms that without a container:
- ML and sensor nodes never run
- HARVEST/UPDATE/SYSTEM intents get a container-link tip
- KNOWLEDGE intent gets a clean answer without the tip
- Off-domain, clarification, and memory recall still work normally

## Run
```bash
.venv\Scripts\python -m tests.test_conversations
```
Expected output: 50/50 passed, score 136/150 (90.7%)
