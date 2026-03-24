# tests/test_intent_router.py

## Purpose
Tests the intent router with 30 sample messages across all 4 intents. Calls the real Groq API.

## How to run
```bash
.venv\Scripts\python -m tests.test_intent_router
```
Requires `GROQ_API_KEY` (or `OPENAI_API_KEY`) in `.env`.

## Test cases (30 total)
| Intent | Count | Examples |
|--------|-------|---------|
| `KNOWLEDGE` | 8 | "What is the ideal pH?", "What causes spirulina to turn yellow?" |
| `UPDATE` | 8 | "Set the pH to 9.5", "Turn on the LED grow lights" |
| `HARVEST` | 7 | "Is it time to harvest?", "What's the optimal OD for harvesting?" |
| `SYSTEM` | 7 | "Is the pump running?", "What is the system status?" |

## Pass criterion
- Accuracy >= 80% → exit code 0
- Below 80% → exit code 1 (fails CI)

## Output format
```
#   Expected    Got         Conf   Match  Message
001 KNOWLEDGE   KNOWLEDGE   0.95     OK   What is the ideal pH...
```
LOW flag shown when confidence < `CONFIDENCE_THRESHOLD` (0.7).

## Known results
~90% accuracy on `llama-3.1-8b-instant`.

## Dependencies
- `agent.intent_router` — `classify_intent`, `CONFIDENCE_THRESHOLD`
- `agent.state` — `AgentState`
