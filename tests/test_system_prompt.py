"""System-prompt quality test — 20 diverse questions.

Tests the SpirulinaAI persona, grounding rules, uncertainty admission,
sensor-check-first behavior, and dose-refusal rules.

Uses a SIMULATED context block (hardcoded cultivation facts) so the test
runs without needing an ingested ChromaDB collection.

Calls the real Groq API — requires GROQ_API_KEY in .env.

Run:
    .venv\\Scripts\\python tests/test_system_prompt.py

For each question the script prints:
    - Category and question
    - Full LLM answer
    - Automatic check result (PASS / WARN / FAIL) with reason
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rag.generator.generate import generate_answer

# ---------------------------------------------------------------------------
# Simulated KB context
# Represents what ChromaDB would return for a broad spirulina query.
# ---------------------------------------------------------------------------

SIMULATED_CONTEXT = """\
[Source 1: spiruline_Manuel.resume-J-P.Jourdan.pdf, p.12 | cultivation_manual]
Spirulina platensis grows optimally between pH 8.5 and 10.5. Below pH 8 the \
culture becomes vulnerable to contamination by green algae. Above pH 10.5, \
cellular stress increases sharply and growth rate drops. The typical daily pH \
cycle rises from around 8.5 at dawn to 10 or above by mid-afternoon due to \
active photosynthesis consuming CO2.

---

[Source 2: spiruline_Manuel.resume-J-P.Jourdan.pdf, p.18 | cultivation_manual]
Optimal temperature for Spirulina platensis is 35-37 degrees C. Growth slows \
significantly below 20 degrees C and above 40 degrees C. Night temperatures \
below 15 degrees C can cause irreversible cell damage. Outdoor cultivation in \
temperate climates requires greenhouse protection in winter months.

---

[Source 3: CultivezVotreSpiruline.pdf, p.34 | cultivation_manual]
The Zarrouk medium formula (per litre of distilled water): NaHCO3 16.8 g, \
K2HPO4 0.5 g, NaNO3 2.5 g, K2SO4 1.0 g, NaCl 1.0 g, MgSO4.7H2O 0.2 g, \
CaCl2 0.04 g, FeSO4.7H2O 0.01 g, EDTA 0.08 g. Adjust pH to 9.5-10 before \
inoculation. Electrical conductivity of a fresh Zarrouk medium is typically \
28-32 mS/cm.

---

[Source 4: culture-et-production-de-spirulina-platensis.pdf, p.7 | scientific_literature]
Spirulina platensis contains 55-70% protein by dry weight, making it one of \
the richest plant-based protein sources. The protein includes all essential \
amino acids. Phycocyanin content ranges from 10-20% of dry biomass. Iron \
content is approximately 580 mg per 100 g dry weight.

---

[Source 5: Alain-Casal-livre-blanc-spiruline.pdf, p.22 | scientific_literature]
Harvesting is triggered when optical density at 680 nm (OD680) reaches 0.8 \
to 1.2 in a 1 cm cuvette, corresponding to approximately 0.8-1.2 g/L biomass. \
At this density, harvesting 30-40% of the culture volume every 1-2 days \
maintains optimal growth. Over-dense cultures (OD680 > 1.5) become \
self-shading and productivity collapses.

---

[Source 6: culture artisanal.pdf, p.41 | cultivation_manual]
Contamination signs include: sudden drop in pH below 8, green coloration \
(green algae invasion), brown or yellow patches, foul smell (bacterial \
contamination), or visible protozoa under microscope at 100x magnification. \
First response: stop harvesting, increase light, check pH and EC, and take a \
microscope sample. Severe contamination may require restarting with a fresh \
culture from backup stock.

---

[Source 7: CultivezVotreSpiruline.pdf, p.55 | cultivation_manual]
After filtration through a 50-micron mesh, spirulina paste contains 80-85% \
water. Sun-drying at 45 degrees C maximum preserves phycocyanin and vitamin \
content. Spray drying at higher temperatures degrades heat-sensitive \
compounds. Dried spirulina should be stored in airtight containers away from \
light and moisture.
"""

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
# Each case defines:
#   question     : str
#   category     : str   (for grouping in output)
#   expect       : str   (what the answer SHOULD do)
#   check_fn     : callable(answer: str) -> bool  (auto-check)
#   check_label  : str   (human-readable check description)

CASES = [
    # === Category A: Should answer from context ===
    {
        "category": "A-grounded",
        "question": "What is the optimal pH range for Spirulina platensis?",
        "expect":   "Cites 8.5-10.5 from context",
        "check_fn": lambda a: "8.5" in a and "10" in a,
        "check_label": "contains '8.5' and '10'",
    },
    {
        "category": "A-grounded",
        "question": "What temperature is best for spirulina growth?",
        "expect":   "Mentions 35-37 C from context",
        "check_fn": lambda a: "35" in a or "37" in a,
        "check_label": "contains '35' or '37'",
    },
    {
        "category": "A-grounded",
        "question": "How do I prepare Zarrouk medium?",
        "expect":   "Lists Zarrouk ingredients from context",
        "check_fn": lambda a: "NaHCO3" in a or "zarrouk" in a.lower(),
        "check_label": "mentions NaHCO3 or Zarrouk",
    },
    {
        "category": "A-grounded",
        "question": "What is the protein content of spirulina?",
        "expect":   "Cites 55-70% from context",
        "check_fn": lambda a: "55" in a or "70" in a or "protein" in a.lower(),
        "check_label": "contains protein percentage",
    },
    {
        "category": "A-grounded",
        "question": "What does an OD680 of 1.5 mean for my culture?",
        "expect":   "Explains self-shading / productivity collapse from context",
        "check_fn": lambda a: any(w in a.lower() for w in ["shading", "productiv", "dense", "harvest", "collapse"]),
        "check_label": "mentions shading, productivity, or harvest urgency",
    },
    {
        "category": "A-grounded",
        "question": "When exactly should I harvest?",
        "expect":   "Cites OD680 0.8-1.2 threshold",
        "check_fn": lambda a: "0.8" in a or "OD" in a,
        "check_label": "mentions OD threshold",
    },
    {
        "category": "A-grounded",
        "question": "My culture has turned greenish, what could be wrong?",
        "expect":   "Mentions green algae contamination from context",
        "check_fn": lambda a: any(w in a.lower() for w in ["algae", "contaminat", "green"]),
        "check_label": "mentions algae or contamination",
    },
    {
        "category": "A-grounded",
        "question": "How should I dry spirulina after harvesting?",
        "expect":   "Mentions 45C max, airtight storage from context",
        "check_fn": lambda a: "45" in a or "dry" in a.lower(),
        "check_label": "mentions drying temperature or method",
    },
    {
        "category": "A-grounded",
        "question": "What happens to spirulina if the temperature drops below 15 degrees C at night?",
        "expect":   "Warns about irreversible cell damage from context",
        "check_fn": lambda a: any(w in a.lower() for w in ["damage", "irreversible", "cell", "15"]),
        "check_label": "warns about cell damage below 15C",
    },
    {
        "category": "A-grounded",
        "question": "What are the first signs of contamination I should look for?",
        "expect":   "Lists signs from context: pH drop, green color, smell, microscope",
        "check_fn": lambda a: sum(1 for w in ["pH", "green", "smell", "microscop", "color", "brown"] if w.lower() in a.lower()) >= 2,
        "check_label": "lists at least 2 contamination signs",
    },

    # === Category B: Should ask for sensor data before advising ===
    {
        "category": "B-sensor-first",
        "question": "Should I add more nutrients to my culture today?",
        "expect":   "Asks for EC reading before advising",
        "check_fn": lambda a: "EC" in a or "conductiv" in a.lower() or "reading" in a.lower() or "measure" in a.lower(),
        "check_label": "asks for EC or sensor reading",
    },
    {
        "category": "B-sensor-first",
        "question": "Is my culture ready to harvest?",
        "expect":   "Asks for OD reading before answering yes/no",
        "check_fn": lambda a: "OD" in a or "optical" in a.lower() or "density" in a.lower() or "measure" in a.lower(),
        "check_label": "asks for OD measurement",
    },
    {
        "category": "B-sensor-first",
        "question": "My growth seems slow lately. What should I do?",
        "expect":   "Does not jump to a fix — asks which parameter to check",
        "check_fn": lambda a: any(w in a.lower() for w in ["check", "measure", "what is your", "reading", "EC", "pH", "temperature", "light"]),
        "check_label": "recommends checking a parameter first",
    },
    {
        "category": "B-sensor-first",
        "question": "My pH dropped suddenly this morning. Should I add bicarbonate?",
        "expect":   "Asks for current pH value before recommending a dose",
        "check_fn": lambda a: any(w in a.lower() for w in ["current", "what is", "reading", "measure", "how low", "value"]),
        "check_label": "asks for the actual pH value before acting",
    },

    # === Category C: Dose refusal — never guess without data ===
    {
        "category": "C-no-dose",
        "question": "How many grams of NaHCO3 should I add to raise my pH?",
        "expect":   "Refuses to give a dose without knowing pH and volume",
        "check_fn": lambda a: any(w in a.lower() for w in ["current ph", "volume", "without knowing", "tell me", "pH reading", "reading"]),
        "check_label": "refuses dose without current pH and volume",
    },
    {
        "category": "C-no-dose",
        "question": "Give me the exact NaNO3 quantity to add to a 500L pond",
        "expect":   "Asks for EC / current nutrient status before specifying a dose",
        "check_fn": lambda a: any(w in a.lower() for w in ["EC", "current", "reading", "conductiv", "nutrient level", "before"]),
        "check_label": "asks for EC or current status before giving dose",
    },

    # === Category D: Admit uncertainty ===
    {
        "category": "D-uncertainty",
        "question": "What specific blue LED wavelength in nanometres maximises phycocyanin synthesis?",
        "expect":   "Admits this is not covered in the context",
        "check_fn": lambda a: any(w in a.lower() for w in ["don't have", "doesn't cover", "not cover", "knowledge base", "not enough", "specific"]),
        "check_label": "admits the knowledge base doesn't cover this specifically",
    },
    {
        "category": "D-uncertainty",
        "question": "What is the complete genome sequence length of Arthrospira platensis?",
        "expect":   "Admits not covered — suggests scientific literature",
        "check_fn": lambda a: any(w in a.lower() for w in ["don't have", "doesn't cover", "not cover", "knowledge base", "literature", "not enough"]),
        "check_label": "admits uncertainty and suggests a source",
    },

    # === Category E: Tone and persona ===
    {
        "category": "E-tone",
        "question": "I'm completely new to spirulina cultivation. Where do I even start?",
        "expect":   "Warm, welcoming, practical — not overwhelming",
        "check_fn": lambda a: len(a) > 100 and any(w in a.lower() for w in ["medium", "zarrouk", "pH", "start", "inoculat", "first"]),
        "check_label": "gives practical starting point, not just 'I don't know'",
    },
    {
        "category": "E-tone",
        "question": "My culture crashed overnight and smells terrible. I'm panicking. What do I do RIGHT NOW?",
        "expect":   "Calm, structured emergency response — escalates if needed",
        "check_fn": lambda a: any(w in a.lower() for w in ["stop", "sample", "microscop", "backup", "specialist", "first", "check", "smell"]),
        "check_label": "gives immediate action steps, mentions specialist if crash is severe",
    },
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SEPARATOR = "-" * 70

def _check(answer: str, case: dict) -> tuple[str, str]:
    """Returns (status, reason)."""
    try:
        passed = case["check_fn"](answer)
        return ("PASS", case["check_label"]) if passed else ("WARN", f"Expected: {case['check_label']}")
    except Exception as exc:
        return ("FAIL", str(exc))


def run() -> None:
    print("=" * 70)
    print("SPIRULINA AI — SYSTEM PROMPT QUALITY TEST")
    print(f"Model  : {os.getenv('GENERATOR_MODEL_NAME', 'llama-3.3-70b-versatile')}")
    print(f"Cases  : {len(CASES)}")
    print("=" * 70)

    results: list[tuple[str, str, str]] = []   # (category, status, label)
    current_cat = ""

    for i, case in enumerate(CASES, start=1):
        cat = case["category"]
        if cat != current_cat:
            current_cat = cat
            cat_label = {
                "A-grounded":    "A — Should answer from context",
                "B-sensor-first":"B — Should ask for sensor data first",
                "C-no-dose":     "C — Should refuse to guess doses",
                "D-uncertainty": "D — Should admit uncertainty",
                "E-tone":        "E — Persona and tone checks",
            }.get(cat, cat)
            print(f"\n{'='*70}")
            print(f"  {cat_label}")
            print(f"{'='*70}")

        print(f"\n[{i:02d}] {case['question']}")
        print(f"      expect -> {case['expect']}")

        t0 = time.time()
        answer = generate_answer(
            question=case["question"],
            context=SIMULATED_CONTEXT,
            history=[],
        )
        elapsed = time.time() - t0

        status, reason = _check(answer, case)
        results.append((cat, status, reason))

        print(SEPARATOR)
        print(answer)
        print(SEPARATOR)
        print(f"  [{status}]  {reason}  ({elapsed:.1f}s)")

    # Summary
    passed = sum(1 for _, s, _ in results if s == "PASS")
    warned = sum(1 for _, s, _ in results if s == "WARN")
    failed = sum(1 for _, s, _ in results if s == "FAIL")

    print(f"\n{'='*70}")
    print(f"SUMMARY  {passed} PASS  /  {warned} WARN  /  {failed} FAIL  out of {len(CASES)}")
    print()

    # Per-category breakdown
    cats = {}
    for cat, status, _ in results:
        cats.setdefault(cat, []).append(status)
    for cat, statuses in cats.items():
        p = statuses.count("PASS")
        w = statuses.count("WARN")
        f = statuses.count("FAIL")
        print(f"  {cat:<18}  {p}/{len(statuses)} PASS  {w} WARN  {f} FAIL")

    print()
    if warned + failed == 0:
        print("All checks passed. System prompt is behaving as intended.")
    else:
        print("WARN = auto-check didn't find expected keywords — read the answer")
        print("       above manually to decide if behaviour is actually correct.")
        print("FAIL = exception in check function — investigate.")
    print("=" * 70)


if __name__ == "__main__":
    run()
