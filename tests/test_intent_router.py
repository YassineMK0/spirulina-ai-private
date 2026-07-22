"""Test the intent router with 30 sample messages across all 4 intents.

Run:
    .venv\\Scripts\\python -m tests.test_intent_router
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from agent.intent_router import classify_intent, CONFIDENCE_THRESHOLD
from agent.state import AgentState

# -- 30 test messages: ~8 per intent ---------------------------------------
TEST_CASES: list[tuple[str, str]] = [
    # ── KNOWLEDGE (8) ─────────────────────────────────────
    ("What is the ideal pH for growing spirulina?",            "KNOWLEDGE"),
    ("How much light does spirulina need per day?",            "KNOWLEDGE"),
    ("What nutrients should I add to the growth medium?",      "KNOWLEDGE"),
    ("What temperature range is optimal for spirulina?",       "KNOWLEDGE"),
    ("Can spirulina grow in tap water?",                       "KNOWLEDGE"),
    ("How long does a typical spirulina growth cycle take?",   "KNOWLEDGE"),
    ("What causes spirulina to turn yellow?",                  "KNOWLEDGE"),
    ("Explain the difference between spirulina and chlorella", "KNOWLEDGE"),

    # ── UPDATE (8) ────────────────────────────────────────
    ("Set the pH to 9.5",                                     "UPDATE"),
    ("Turn on the LED grow lights",                           "UPDATE"),
    ("Change the temperature to 32 degrees",                  "UPDATE"),
    ("Increase the stirring speed to 60 rpm",                 "UPDATE"),
    ("Turn off the heater",                                   "UPDATE"),
    ("Adjust the nutrient dosing to 5 ml per hour",           "UPDATE"),
    ("Switch the light cycle to 16 hours on",                 "UPDATE"),
    ("Lower the CO2 injection rate",                          "UPDATE"),

    # ── HARVEST (7) ───────────────────────────────────────
    ("Is it time to harvest?",                                "HARVEST"),
    ("What is the current biomass density?",                  "HARVEST"),
    ("Schedule a harvest for tomorrow morning",               "HARVEST"),
    ("How do I know when spirulina is ready to harvest?",     "HARVEST"),
    ("Start the harvest process now",                         "HARVEST"),
    ("What's the optimal OD for harvesting?",                 "HARVEST"),
    ("How much dry weight can I expect from this batch?",     "HARVEST"),

    # ── SYSTEM (7) ────────────────────────────────────────
    ("Is the pump running?",                                  "SYSTEM"),
    ("Show me the latest sensor errors",                      "SYSTEM"),
    ("What is the system status?",                            "SYSTEM"),
    ("Are there any active alerts?",                          "SYSTEM"),
    ("Check if the temperature sensor is online",             "SYSTEM"),
    ("When was the last sensor reading?",                     "SYSTEM"),
    ("Reboot the controller",                                 "SYSTEM"),
]


def _make_state(message: str) -> AgentState:
    return {
        "user_id": "test-user",
        "container_id": "container-42",
        "has_container": True,
        "chat_history": [{"role": "user", "content": message}],
    }


def main() -> None:
    provider = os.getenv("INTENT_MODEL_PROVIDER", "groq").lower()
    groq_key = os.getenv("GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if provider not in ("groq", "openai", "ollama"):
        print(f"ERROR: Unsupported INTENT_MODEL_PROVIDER: {provider!r}")
        sys.exit(1)
    if provider == "groq" and not groq_key:
        print("ERROR: Set GROQ_API_KEY in .env to run this test with INTENT_MODEL_PROVIDER=groq.")
        sys.exit(1)
    if provider == "openai" and not openai_key:
        print("ERROR: Set OPENAI_API_KEY in .env to run this test with INTENT_MODEL_PROVIDER=openai.")
        sys.exit(1)
    # provider == "ollama": no API key needed, just a reachable local server

    passed = 0
    failed = 0
    low_confidence = 0
    results: list[dict] = []

    print(f"Running {len(TEST_CASES)} intent classification tests ...\n")
    print(f"{'#':<3} {'Expected':<11} {'Got':<11} {'Conf':>6} {'Match':>6}  Message")
    print("-" * 95)

    for i, (message, expected) in enumerate(TEST_CASES, 1):
        state = _make_state(message)
        out = classify_intent(state)
        got_intent = out["intent"]
        got_conf = out["confidence"]
        match = got_intent == expected
        if match:
            passed += 1
        else:
            failed += 1
        if got_conf < CONFIDENCE_THRESHOLD:
            low_confidence += 1

        flag = "OK" if match else "FAIL"
        conf_flag = " LOW" if got_conf < CONFIDENCE_THRESHOLD else ""
        print(f"{i:<3} {expected:<11} {got_intent:<11} {got_conf:>5.2f}  {flag:>4}{conf_flag}  {message[:55]}")

        results.append({
            "message": message,
            "expected": expected,
            "got": got_intent,
            "confidence": got_conf,
            "match": match,
        })

    # -- summary -----------------------------------------------------------
    total = len(TEST_CASES)
    accuracy = passed / total * 100
    print("-" * 95)
    print(f"\nResults: {passed}/{total} correct ({accuracy:.1f}% accuracy)")
    print(f"Failed:  {failed}")
    print(f"Low confidence (<{CONFIDENCE_THRESHOLD}): {low_confidence}")

    if failed > 0:
        print("\nFailed cases:")
        for r in results:
            if not r["match"]:
                print(f"  - expected {r['expected']}, got {r['got']} "
                      f"({r['confidence']:.2f}): {r['message'][:60]}")

    # exit code for CI
    sys.exit(0 if accuracy >= 80 else 1)


if __name__ == "__main__":
    main()
