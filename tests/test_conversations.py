"""50 full conversation scenario tests.

Categories
----------
A. Pure knowledge questions         (10 scenarios, IDs A01-A10)
B. Multi-turn dialogs with follow-ups (10 scenarios, IDs B01-B10)
C. Troubleshooting flows            (10 scenarios, IDs C01-C10)
D. Harvest timing questions         (10 scenarios, IDs D01-D10)
E. No container -> RAG-only mode     (10 scenarios, IDs E01-E10)

Scoring per scenario (3 points max)
------------------------------------
1. Intent routed correctly          (+1)
2. Response is non-empty            (+1)
3. Response contains expected token (+1)

Run:
    .venv\\Scripts\\python -m tests.test_conversations
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import graph

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASS_THRESHOLD = 2          # minimum score to consider a scenario passing
SECTION_WIDTH  = 65


# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------

class Scenario:
    """A single conversation test case."""

    def __init__(
        self,
        sid: str,
        description: str,
        state: dict[str, Any],
        mock_intent: str,
        mock_confidence: float,
        expected_intent: str,
        expected_tokens: list[str],        # at least one must appear in response
        expected_nodes_run: list[str],     # substring matches in captured stdout
        expected_nodes_skip: list[str],    # these must NOT appear in stdout
    ):
        self.sid               = sid
        self.description       = description
        self.state             = state
        self.mock_intent       = mock_intent
        self.mock_confidence   = mock_confidence
        self.expected_intent   = expected_intent
        self.expected_tokens   = expected_tokens
        self.expected_nodes_run  = expected_nodes_run
        self.expected_nodes_skip = expected_nodes_skip


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _state(
    message: str,
    container_id: str = "",
    history: list[dict] | None = None,
) -> dict[str, Any]:
    chat = list(history or [])
    chat.append({"role": "user", "content": message})
    return {
        "user_id":      "test-user",
        "container_id": container_id,
        "chat_history": chat,
    }


def _with_container(message: str, history: list[dict] | None = None) -> dict[str, Any]:
    return _state(message, container_id="container-42", history=history)


def _no_container(message: str, history: list[dict] | None = None) -> dict[str, Any]:
    return _state(message, container_id="", history=history)


def _chain(intent: str, confidence: float) -> MagicMock:
    m = MagicMock()
    m.invoke.return_value = f'{{"intent": "{intent}", "confidence": {confidence}}}'
    return m


def _run(scenario: Scenario) -> tuple[dict, str]:
    """Run graph with mocked LLM chain. Returns (result, stdout)."""
    buf = io.StringIO()
    with patch("agent.intent_router._get_chain",
               return_value=_chain(scenario.mock_intent, scenario.mock_confidence)):
        with contextlib.redirect_stdout(buf):
            result = graph.invoke(scenario.state)
    return result, buf.getvalue()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score(scenario: Scenario, result: dict, stdout: str) -> tuple[int, list[str]]:
    """Return (score, list_of_failure_reasons)."""
    score   = 0
    reasons = []

    # 1. Intent correctly routed
    actual_intent = result.get("intent", "")
    if actual_intent == scenario.expected_intent:
        score += 1
    else:
        reasons.append(f"intent: expected={scenario.expected_intent!r} got={actual_intent!r}")

    # 2. Response non-empty
    response = result.get("response", "")
    if response.strip():
        score += 1
    else:
        reasons.append("response: empty")

    # 3. Expected token in response
    lower = response.lower()
    if scenario.expected_tokens:
        if any(tok.lower() in lower for tok in scenario.expected_tokens):
            score += 1
        else:
            reasons.append(
                f"content: none of {scenario.expected_tokens!r} found in response"
            )
    else:
        score += 1  # no token requirement -> free point

    # Bonus checks (no score impact, only warnings)
    for node in scenario.expected_nodes_run:
        if node not in stdout:
            reasons.append(f"routing: expected node {node!r} did not run")

    for node in scenario.expected_nodes_skip:
        if node in stdout:
            reasons.append(f"routing: node {node!r} ran but should have been skipped")

    return score, reasons


# ---------------------------------------------------------------------------
# Scenario definitions - A: Pure Knowledge
# ---------------------------------------------------------------------------

SCENARIOS_A = [
    Scenario(
        sid="A01", description="Optimal pH range for spirulina",
        state=_no_container("What is the optimal pH for spirulina cultivation?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.97,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ph", "8", "9", "10", "alkalin", "optimal"],
        expected_nodes_run=["[node] retrieve_rag", "[node] generate_response"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="A02", description="Temperature range for growth",
        state=_no_container("What temperature should I maintain for spirulina?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.95,
        expected_intent="KNOWLEDGE",
        expected_tokens=["temperature", "35", "30", "celsius", "warm"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models"],
    ),
    Scenario(
        sid="A03", description="Light requirements",
        state=_no_container("How much light does spirulina need per day?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.93,
        expected_intent="KNOWLEDGE",
        expected_tokens=["light", "lux", "hour", "photoperiod", "sun", "illu"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models"],
    ),
    Scenario(
        sid="A04", description="Nutrient solution composition",
        state=_no_container("What nutrients does spirulina need to grow?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.94,
        expected_intent="KNOWLEDGE",
        expected_tokens=["nitrogen", "nutrient", "sodium", "bicarbonate", "zarrouk", "mineral"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models"],
    ),
    Scenario(
        sid="A05", description="What is OD680",
        state=_no_container("What does OD680 mean and why is it important?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.96,
        expected_intent="KNOWLEDGE",
        expected_tokens=["od", "optical", "density", "biomass", "680", "absorbance"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="A06", description="Spirulina protein content",
        state=_no_container("How much protein does spirulina contain?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.95,
        expected_intent="KNOWLEDGE",
        expected_tokens=["protein", "%", "60", "70", "amino", "content"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models"],
    ),
    Scenario(
        sid="A07", description="EC conductivity meaning",
        state=_no_container("What is EC and what range is acceptable for spirulina?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.93,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ec", "conductivity", "ms", "mineral", "salt", "electr"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="A08", description="How spirulina reproduces",
        state=_no_container("How does spirulina reproduce?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.92,
        expected_intent="KNOWLEDGE",
        expected_tokens=["division", "cell", "fragment", "filament", "reproduc", "grow"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="A09", description="Difference between spirulina species",
        state=_no_container("What is the difference between Spirulina platensis and maxima?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.91,
        expected_intent="KNOWLEDGE",
        expected_tokens=["platensis", "maxima", "species", "arthrospira", "differ"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="A10", description="Greeting treated as KNOWLEDGE not OFF_DOMAIN",
        state=_no_container("Hello! What can you help me with?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.88,
        expected_intent="KNOWLEDGE",
        expected_tokens=["spirulina", "help", "cultivation", "question", "assist"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] reject_off_domain"],
    ),
]


# ---------------------------------------------------------------------------
# Scenario definitions - B: Multi-turn dialogs
# ---------------------------------------------------------------------------

_PH_HISTORY = [
    {"role": "user",      "content": "What is the optimal pH for spirulina?"},
    {"role": "assistant", "content": "The optimal pH for spirulina is between 8.5 and 10.5."},
]

_HARVEST_HISTORY = [
    {"role": "user",      "content": "How do I know when to harvest spirulina?"},
    {"role": "assistant", "content": "You should harvest when OD680 reaches 1.0 to 1.2 g/L."},
]

SCENARIOS_B = [
    Scenario(
        sid="B01", description="Follow-up on pH - 'what happens if it drops?'",
        state=_no_container("What happens if it drops below 8?", history=_PH_HISTORY),
        mock_intent="KNOWLEDGE", mock_confidence=0.91,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ph", "acid", "drop", "below", "low", "effect", "growth"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B02", description="Follow-up on harvest - 'what if I wait too long?'",
        state=_no_container("What if I wait too long?", history=_HARVEST_HISTORY),
        mock_intent="KNOWLEDGE", mock_confidence=0.89,
        expected_intent="KNOWLEDGE",
        expected_tokens=["harvest", "late", "self-shad", "density", "too long", "risk", "od"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B03", description="Two-turn: ask about nutrients then follow up with 'how much'",
        state=_no_container("How much should I add?", history=[
            {"role": "user",      "content": "What nutrients does spirulina need?"},
            {"role": "assistant", "content": "It needs nitrogen, phosphorus, and bicarbonate."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.88,
        expected_intent="KNOWLEDGE",
        expected_tokens=["dose", "gram", "litre", "liter", "add", "amount", "concentration", "mg"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B04", description="Multi-turn troubleshooting: yellow color follow-up",
        state=_no_container("Could this also cause slow growth?", history=[
            {"role": "user",      "content": "My spirulina is turning yellow."},
            {"role": "assistant", "content": "Yellow color usually indicates nitrogen deficiency."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.90,
        expected_intent="KNOWLEDGE",
        expected_tokens=["growth", "nitrogen", "slow", "deficien", "yellow", "affect"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B05", description="Three-turn dialog: contamination -> cause -> prevention",
        state=_no_container("How do I prevent it from coming back?", history=[
            {"role": "user",      "content": "I see green patches in my culture."},
            {"role": "assistant", "content": "Green patches can indicate green algae contamination."},
            {"role": "user",      "content": "How did the contamination get in?"},
            {"role": "assistant", "content": "It can enter via unsterilized equipment or airborne spores."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.92,
        expected_intent="KNOWLEDGE",
        expected_tokens=["steriliz", "prevent", "clean", "contaminat", "hygiene", "filter"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B06", description="Follow-up pronoun: 'when should I do it?'",
        state=_no_container("When should I do it?", history=[
            {"role": "user",      "content": "How do I adjust the EC of my culture?"},
            {"role": "assistant", "content": "You can adjust EC by adding more nutrient solution."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.87,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ec", "nutrient", "adjust", "morning", "when", "time", "measur"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B07", description="Memory recall mid-conversation",
        state=_no_container("What did I ask you earlier?", history=_PH_HISTORY),
        mock_intent="MEMORY_RECALL", mock_confidence=0.94,
        expected_intent="MEMORY_RECALL",
        expected_tokens=["ph", "optimal", "8.5", "you", "asked", "earlier", "conversation"],
        expected_nodes_run=["[node] recall_memory"],
        expected_nodes_skip=["[node] retrieve_rag", "[node] run_ml_models"],
    ),
    Scenario(
        sid="B08", description="Context switch: from pH to harvest in same session",
        state=_no_container("Now tell me about harvest timing.", history=_PH_HISTORY),
        mock_intent="HARVEST", mock_confidence=0.93,
        expected_intent="HARVEST",
        expected_tokens=["harvest", "od", "density", "timing", "ready"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B09", description="Follow-up after troubleshooting: ask for step-by-step",
        state=_no_container("Can you give me the steps in order?", history=[
            {"role": "user",      "content": "My pH is dropping fast."},
            {"role": "assistant", "content": "Fast pH drop suggests CO2 build-up or acid contamination."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.89,
        expected_intent="KNOWLEDGE",
        expected_tokens=["step", "first", "check", "add", "measure", "ph", "action"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="B10", description="User says thank you then asks new question",
        state=_no_container("Thanks! One more thing - how often should I stir?", history=[
            {"role": "user",      "content": "What pH is best?"},
            {"role": "assistant", "content": "8.5 to 10.5 is the optimal range."},
        ]),
        mock_intent="KNOWLEDGE", mock_confidence=0.91,
        expected_intent="KNOWLEDGE",
        expected_tokens=["stir", "agitat", "mix", "often", "hour", "time", "rotat"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
]


# ---------------------------------------------------------------------------
# Scenario definitions - C: Troubleshooting flows
# ---------------------------------------------------------------------------

SCENARIOS_C = [
    Scenario(
        sid="C01", description="pH dropping below 8 - diagnosis + action",
        state=_no_container("My pH dropped to 7.8 overnight. What should I do?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.94,
        expected_intent="KNOWLEDGE",
        expected_tokens=["bicarbonate", "sodium", "add", "ph", "raise", "correct", "soda"],
        expected_nodes_run=["[node] retrieve_rag", "[node] generate_response"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C02", description="Yellow/pale color - nitrogen deficiency",
        state=_no_container("My spirulina is turning yellow-green. What does this mean?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.93,
        expected_intent="KNOWLEDGE",
        expected_tokens=["nitrogen", "yellow", "deficien", "nutrient", "pale", "color"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C03", description="White foam on surface",
        state=_no_container("There is white foam forming on the surface of my culture. Is this normal?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.92,
        expected_intent="KNOWLEDGE",
        expected_tokens=["foam", "protein", "agitat", "surface", "normal", "bubble"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C04", description="Strong smell / bad odor",
        state=_no_container("My culture has a very strong bad smell. What is wrong?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.94,
        expected_intent="KNOWLEDGE",
        expected_tokens=["smell", "odor", "contaminat", "bacteria", "decay", "rotten", "anaerob"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C05", description="Culture not growing - slow growth",
        state=_no_container("My spirulina has barely grown in 5 days. What could cause this?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.95,
        expected_intent="KNOWLEDGE",
        expected_tokens=["growth", "slow", "nutrient", "temperature", "light", "ph", "cause"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C06", description="Green algae contamination",
        state=_no_container("I see green spots forming in my spirulina. Could it be contamination?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.93,
        expected_intent="KNOWLEDGE",
        expected_tokens=["contaminat", "green algae", "chlorella", "competitor", "ph", "alkalin"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C07", description="EC too high - salt build-up",
        state=_no_container("My EC reading is 45 mS/cm. Is that too high and what should I do?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.92,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ec", "high", "dilute", "water", "salt", "conductiv", "add"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C08", description="Temperature too high - 42C heat wave",
        state=_no_container("It got very hot and my culture temperature hit 42C. Is it damaged?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.94,
        expected_intent="KNOWLEDGE",
        expected_tokens=["temperature", "heat", "42", "stress", "cool", "shade", "damage"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C09", description="Culture crashed - completely dark/black",
        state=_no_container("My culture turned dark brown and smells terrible. I think it crashed."),
        mock_intent="KNOWLEDGE", mock_confidence=0.96,
        expected_intent="KNOWLEDGE",
        expected_tokens=["crash", "dead", "restart", "contaminat", "dark", "new", "fresh"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="C10", description="Bubbles appearing - CO2 or fermentation?",
        state=_no_container("Small bubbles are forming at the surface. Is this photosynthesis or a problem?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.91,
        expected_intent="KNOWLEDGE",
        expected_tokens=["bubble", "oxygen", "co2", "photosynthes", "normal", "gas"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
]


# ---------------------------------------------------------------------------
# Scenario definitions - D: Harvest timing
# ---------------------------------------------------------------------------

SCENARIOS_D = [
    Scenario(
        sid="D01", description="Harvest decision - OD at optimal level, no container",
        state=_no_container("My OD680 is 1.1 g/L and stable for 2 days. Should I harvest?"),
        mock_intent="HARVEST", mock_confidence=0.95,
        expected_intent="HARVEST",
        expected_tokens=["harvest", "od", "1.1", "ready", "optimal", "density"],
        expected_nodes_run=["[node] retrieve_rag", "[node] reasoning_agent"],
        expected_nodes_skip=["[node] run_ml_models", "[node] generate_response"],
    ),
    Scenario(
        sid="D02", description="Harvest decision - OD too low",
        state=_no_container("OD680 is 0.4. Should I harvest?"),
        mock_intent="HARVEST", mock_confidence=0.94,
        expected_intent="HARVEST",
        expected_tokens=["low", "wait", "od", "0.4", "not yet", "grow", "density"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D03", description="Partial vs full harvest",
        state=_no_container("Should I do a partial harvest or harvest everything?"),
        mock_intent="HARVEST", mock_confidence=0.93,
        expected_intent="HARVEST",
        expected_tokens=["partial", "harvest", "percent", "%", "inoculum", "keep"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D04", description="Harvest frequency - how often",
        state=_no_container("How often should I harvest spirulina?"),
        mock_intent="HARVEST", mock_confidence=0.92,
        expected_intent="HARVEST",
        expected_tokens=["harvest", "frequen", "day", "week", "often", "interval", "cycle"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D05", description="Best time of day to harvest",
        state=_no_container("What time of day is best to harvest spirulina?"),
        mock_intent="HARVEST", mock_confidence=0.91,
        expected_intent="HARVEST",
        expected_tokens=["morning", "early", "time", "day", "protein", "harvest", "light"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D06", description="Harvest method - filtration",
        state=_no_container("How do I actually harvest spirulina? What equipment do I need?"),
        mock_intent="HARVEST", mock_confidence=0.93,
        expected_intent="HARVEST",
        expected_tokens=["filter", "mesh", "screen", "press", "cloth", "harvest", "equip"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D07", description="Post-harvest drying",
        state=_no_container("After harvesting, how should I dry the spirulina?"),
        mock_intent="HARVEST", mock_confidence=0.92,
        expected_intent="HARVEST",
        expected_tokens=["dry", "sun", "temperature", "spray", "powder", "method"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D08", description="How to refill after harvest",
        state=_no_container("After I harvest 30%, what do I add back to the container?"),
        mock_intent="HARVEST", mock_confidence=0.91,
        expected_intent="HARVEST",
        expected_tokens=["refill", "water", "nutrient", "volume", "add", "solution", "replace"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D09", description="Harvest yield calculation",
        state=_no_container("How much dry spirulina can I expect from 100 liters?"),
        mock_intent="HARVEST", mock_confidence=0.93,
        expected_intent="HARVEST",
        expected_tokens=["gram", "liter", "yield", "dry", "100", "g/l", "biomass"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
    Scenario(
        sid="D10", description="French harvest question",
        state=_no_container("Quand dois-je récolter ma spiruline?"),
        mock_intent="HARVEST", mock_confidence=0.92,
        expected_intent="HARVEST",
        expected_tokens=["récolte", "harvest", "od", "densité", "density", "gramme"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=[],
    ),
]


# ---------------------------------------------------------------------------
# Scenario definitions - E: No container -> RAG-only mode
# ---------------------------------------------------------------------------

SCENARIOS_E = [
    Scenario(
        sid="E01", description="HARVEST intent, no container -> RAG-only + tip",
        state=_no_container("Should I harvest my spirulina today?"),
        mock_intent="HARVEST", mock_confidence=0.94,
        expected_intent="HARVEST",
        expected_tokens=["container", "harvest", "od", "sensor"],
        expected_nodes_run=["[node] retrieve_rag", "[node] reasoning_agent"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E02", description="UPDATE intent, no container -> tip shown",
        state=_no_container("Set the pH to 9.5"),
        mock_intent="UPDATE", mock_confidence=0.95,
        expected_intent="UPDATE",
        expected_tokens=["container", "link", "ph", "sensor", "no container"],
        expected_nodes_run=["[node] retrieve_rag", "[node] generate_response"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E03", description="SYSTEM intent, no container -> tip shown",
        state=_no_container("What is the status of my culture right now?"),
        mock_intent="SYSTEM", mock_confidence=0.93,
        expected_intent="SYSTEM",
        expected_tokens=["container", "link", "sensor", "monitor"],
        expected_nodes_run=["[node] retrieve_rag", "[node] reasoning_agent"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E04", description="KNOWLEDGE intent, no container -> no tip, clean answer",
        state=_no_container("What is the optimal pH for spirulina?"),
        mock_intent="KNOWLEDGE", mock_confidence=0.97,
        expected_intent="KNOWLEDGE",
        expected_tokens=["ph", "8", "9", "optimal"],
        expected_nodes_run=["[node] retrieve_rag", "[node] generate_response"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E05", description="No container - ML nodes must NOT run",
        state=_no_container("I want a growth prediction for my culture."),
        mock_intent="KNOWLEDGE", mock_confidence=0.91,
        expected_intent="KNOWLEDGE",
        expected_tokens=["growth", "predict", "od", "factor", "influenc"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E06", description="No container - HARVEST + tip mentions container link",
        state=_no_container("My OD is 1.2. Can I harvest?"),
        mock_intent="HARVEST", mock_confidence=0.95,
        expected_intent="HARVEST",
        expected_tokens=["od", "1.2", "harvest", "container"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models"],
    ),
    Scenario(
        sid="E07", description="No container - sensor read must NOT happen",
        state=_no_container("What is my current temperature?"),
        mock_intent="SYSTEM", mock_confidence=0.90,
        expected_intent="SYSTEM",
        expected_tokens=["container", "sensor", "temperature", "link", "monitor"],
        expected_nodes_run=["[node] retrieve_rag"],
        expected_nodes_skip=["[node] run_ml_models", "[node] read_sensors"],
    ),
    Scenario(
        sid="E08", description="No container - off-domain still works",
        state=_no_container("What is the capital of France?"),
        mock_intent="OFF_DOMAIN", mock_confidence=0.96,
        expected_intent="OFF_DOMAIN",
        expected_tokens=["spirulina", "outside", "domain", "speciali", "help"],
        expected_nodes_run=["[node] reject_off_domain"],
        expected_nodes_skip=["[node] retrieve_rag", "[node] run_ml_models"],
    ),
    Scenario(
        sid="E09", description="No container - clarification still works",
        state=_no_container("uh the thing about the stuff"),
        mock_intent="UNKNOWN", mock_confidence=0.35,
        expected_intent="UNKNOWN",
        expected_tokens=["specific", "asking", "knowledge", "troubleshoot", "clarif"],
        expected_nodes_run=["[node] request_clarification"],
        expected_nodes_skip=["[node] retrieve_rag", "[node] run_ml_models"],
    ),
    Scenario(
        sid="E10", description="No container - memory recall works without container",
        state=_no_container("What did we talk about before?", history=_PH_HISTORY),
        mock_intent="MEMORY_RECALL", mock_confidence=0.93,
        expected_intent="MEMORY_RECALL",
        expected_tokens=["ph", "optimal", "8.5", "conversation", "earlier", "you"],
        expected_nodes_run=["[node] recall_memory"],
        expected_nodes_skip=["[node] retrieve_rag", "[node] run_ml_models"],
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_SCENARIOS: list[Scenario] = (
    SCENARIOS_A + SCENARIOS_B + SCENARIOS_C + SCENARIOS_D + SCENARIOS_E
)


def run_all() -> int:
    """Run all scenarios. Returns exit code (0=all pass, 1=failures)."""
    totals = {"passed": 0, "failed": 0, "score": 0, "max_score": 0}
    section_results: dict[str, tuple[int, int]] = {}   # section -> (passed, total)

    categories = {
        "A": "Pure Knowledge Questions",
        "B": "Multi-Turn Dialogs",
        "C": "Troubleshooting Flows",
        "D": "Harvest Timing",
        "E": "No Container - RAG-Only Mode",
    }

    all_failures: list[tuple[str, str, list[str]]] = []

    for letter, label in categories.items():
        scenarios = [s for s in ALL_SCENARIOS if s.sid.startswith(letter)]
        sec_pass = 0

        print(f"\n{'=' * SECTION_WIDTH}")
        print(f"  {letter}. {label}  ({len(scenarios)} scenarios)")
        print(f"{'=' * SECTION_WIDTH}")

        for s in scenarios:
            totals["max_score"] += 3
            try:
                result, stdout = _run(s)
                score, reasons = _score(s, result, stdout)
            except Exception as exc:
                score   = 0
                reasons = [f"EXCEPTION: {type(exc).__name__}: {exc}"]
                result  = {}

            totals["score"] += score
            passed = score >= PASS_THRESHOLD

            if passed:
                totals["passed"] += 1
                sec_pass += 1
                status = "PASS"
            else:
                totals["failed"] += 1
                status = "FAIL"
                all_failures.append((s.sid, s.description, reasons))

            score_str = f"{score}/3"
            print(f"  [{status}] {s.sid}  {score_str:>3}  {s.description}")
            for r in reasons:
                print(f"           ! {r}")

        section_results[letter] = (sec_pass, len(scenarios))

    # Summary
    total = totals["passed"] + totals["failed"]
    pct   = totals["score"] / max(totals["max_score"], 1) * 100

    print(f"\n{'=' * SECTION_WIDTH}")
    print(f"  RESULTS SUMMARY")
    print(f"{'=' * SECTION_WIDTH}")
    for letter, label in categories.items():
        p, t = section_results[letter]
        bar = "#" * p + "." * (t - p)
        print(f"  {letter}. [{bar}] {p}/{t}  {label}")

    print(f"\n  Total scenarios : {total}")
    print(f"  Passed          : {totals['passed']}")
    print(f"  Failed          : {totals['failed']}")
    print(f"  Score           : {totals['score']}/{totals['max_score']}  ({pct:.1f}%)")

    if all_failures:
        print(f"\n{'=' * SECTION_WIDTH}")
        print(f"  FAILURES ({len(all_failures)})")
        print(f"{'=' * SECTION_WIDTH}")
        for sid, desc, reasons in all_failures:
            print(f"\n  {sid}: {desc}")
            for r in reasons:
                print(f"    - {r}")

    print()
    return 0 if totals["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
