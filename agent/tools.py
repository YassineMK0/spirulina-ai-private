"""Domain tools for the SpirulinaAI agentic loop.

Pure-Python calculations + thin service wrappers.
The agentic LLM calls these to produce verifiable outputs
instead of hallucinating doses or diagnoses.

Available tools
---------------
calculate_ph_correction     -- dose of NaHCO3 / HCl to hit target pH
calculate_ec_correction     -- nutrient addition or dilution to hit target EC
diagnose_culture_symptom    -- structured diagnostic checklist for visible symptoms
format_action_plan          -- format final checklist as markdown
"""
from __future__ import annotations

from langchain_core.tools import tool


# ── pH Correction ─────────────────────────────────────────────────────────────

@tool
def calculate_ph_correction(
    current_ph: float,
    target_ph: float,
    volume_liters: float,
) -> str:
    """Calculate the dose of pH corrector needed to reach target pH.

    Returns a step-by-step markdown action plan.
    Call this BEFORE recommending any pH-altering chemical.

    Args:
        current_ph: Current measured pH (e.g. 8.2)
        target_ph: Desired pH — spirulina optimal 9.5–10.2
        volume_liters: Total culture volume in litres
    """
    delta = round(target_ph - current_ph, 2)

    if abs(delta) < 0.05:
        return f"**No adjustment needed** — pH {current_ph} is already at target {target_ph}."

    if delta > 0:
        # Raise pH with NaHCO3
        # Empirical rule: ~0.8 g NaHCO3 per 10 L raises pH by ~0.1 unit (Zarrouk buffer)
        dose_g = abs(delta) * 8.0 * (volume_liters / 10.0)
        corrector = "NaHCO3 (sodium bicarbonate)"
        direction = "raise"
        safety = "Excess bicarbonate can spike pH above 10.8 — always add in increments and re-measure."
    else:
        # Lower pH with CO2 insufflation (preferred) or dilute HCl
        # ~0.1 mL HCl (1 M) per 10 L lowers pH by ~0.1 unit
        dose_g = abs(delta) * 1.0 * (volume_liters / 10.0)
        corrector = "CO2 injection (preferred) or dilute HCl 0.1 M"
        direction = "lower"
        safety = "HCl is corrosive — pre-dilute to 0.1 M before adding. Never add concentrated acid directly."

    first_add = round(dose_g * 0.4, 1)

    return f"""## pH Correction Plan

| Parameter | Value |
|-----------|-------|
| Current pH | {current_ph} |
| Target pH | {target_ph} |
| Delta | {'+' if delta > 0 else ''}{delta} units |
| Volume | {volume_liters:.0f} L |
| Corrector | {corrector} |
| **Estimated total dose** | **{dose_g:.1f} g** |

### Procedure
1. Dissolve **{first_add} g** (40 % of total) in 500 mL of culture water
2. Add slowly at the return flow point while stirring — never pour directly onto cells
3. Wait **15 min**, then re-measure pH
4. Repeat with remaining dose, adjusting based on new reading
5. Log each addition with timestamp

> ⚠️ {safety}
> Estimates assume standard Zarrouk buffering (~2 mS/cm EC). Your culture may need ±30 % adjustment.
"""


# ── EC / Nutrient Correction ──────────────────────────────────────────────────

@tool
def calculate_ec_correction(
    current_ec_ms: float,
    target_ec_ms: float,
    volume_liters: float,
) -> str:
    """Calculate nutrient addition or dilution volume to reach target EC.

    Returns a markdown action plan with specific amounts.
    Call this BEFORE recommending any nutrient adjustment.

    Args:
        current_ec_ms: Current EC in mS/cm
        target_ec_ms: Target EC in mS/cm — Zarrouk optimal 2.0–3.5 mS/cm
        volume_liters: Culture volume in litres
    """
    delta = round(target_ec_ms - current_ec_ms, 2)

    if abs(delta) < 0.05:
        return f"**No adjustment needed** — EC {current_ec_ms} mS/cm is already at target {target_ec_ms} mS/cm."

    if delta > 0:
        # Add concentrated nutrient solution
        # Standard Zarrouk: target ~2.5 mS/cm ≈ 2.5 g/L dissolved salts
        # Linear approximation: 1 mS/cm ≈ 1 g/L addition
        salts_g = delta * volume_liters
        first_add = round(salts_g * 0.5, 0)

        return f"""## EC Correction Plan — Nutrient Addition

| Parameter | Value |
|-----------|-------|
| Current EC | {current_ec_ms} mS/cm |
| Target EC | {target_ec_ms} mS/cm |
| Delta | +{delta} mS/cm |
| Volume | {volume_liters:.0f} L |
| **Estimated nutrient salts** | **{salts_g:.0f} g** Zarrouk medium |

### Procedure
1. Dissolve **{first_add:.0f} g** in 2 L of warm water (50 % of total)
2. Add to culture while stirring — distribute along the whole pond length
3. Wait **30 min**, then re-measure EC
4. Add remaining half if target not reached
5. Never exceed +0.5 mS/cm per hour (osmotic shock risk)

> ⚠️ If EC was low for >48 h, check for yellowing — the culture may be nitrogen-starved.
> These figures assume standard Zarrouk formulation. Adjust for your specific recipe.
"""
    else:
        # Dilute with fresh water
        # target_ec = current_ec * V / (V + added_water)  →  added = V * (current/target - 1)
        water_to_add = volume_liters * (current_ec_ms / target_ec_ms - 1.0)

        return f"""## EC Correction Plan — Dilution

| Parameter | Value |
|-----------|-------|
| Current EC | {current_ec_ms} mS/cm |
| Target EC | {target_ec_ms} mS/cm |
| Delta | {delta} mS/cm |
| Volume | {volume_liters:.0f} L |
| **Water to add** | **{water_to_add:.1f} L** dechlorinated water |

### Procedure
1. Prepare **{water_to_add:.1f} L** of clean, dechlorinated water at culture temperature (±2 °C)
2. Add over **60 min** — do not dump all at once (osmotic shock)
3. Re-measure EC every 20 min during addition
4. Scale aeration rate proportionally to new volume
5. After dilution verify pH — rapid volume change sometimes shifts it

> ⚠️ Rapid dilution above +20 % culture volume can stress cells — stay gradual.
"""


# ── Culture Diagnosis ─────────────────────────────────────────────────────────

@tool
def diagnose_culture_symptom(symptom_description: str) -> str:
    """Structured diagnostic checklist for a visible or measurable symptom.

    Use when the operator reports a visual change or observable problem.
    Covers colour changes, foam, odour, slow growth, and crash scenarios.

    Args:
        symptom_description: What the operator observes — e.g. "culture is turning yellow"
    """
    s = symptom_description.lower()

    DIAGNOSES = [
        {
            "triggers": ["yellow", "pale", "jaune", "pâle", "light green", "vert clair", "lighten"],
            "title": "Nitrogen or Iron Deficiency",
            "severity": "WARNING",
            "cause": (
                "Loss of phycocyanin (blue-green pigment) caused by nitrogen starvation "
                "or iron depletion. Without nitrogen the cell cannot rebuild chlorophyll."
            ),
            "checks": [
                "EC — if below 1.5 mS/cm the medium is depleted",
                "Last full nutrient refresh — if >7 days, deficiency likely",
                "Iron chelate addition — if >14 days, iron may be limiting",
                "Microscopy — filaments should still be spiral and intact",
            ],
            "actions": [
                "Measure EC now — if <1.5 mS/cm add fresh Zarrouk medium immediately",
                "Add iron chelate (EDTA-Fe): 0.01 g/L if not added in the past 10 days",
                "Cut harvest rate by 50 % for 3–5 days to let biomass recover",
                "Increase aeration to improve CO₂/O₂ exchange",
            ],
            "critical": False,
        },
        {
            "triggers": ["foam", "mousse", "froth", "bubble", "bulle", "scum"],
            "title": "Surface Foam — Possible Contamination",
            "severity": "CRITICAL",
            "cause": (
                "Persistent foam usually signals bacterial contamination (heterotrophs "
                "competing with spirulina) or protein precipitation from a crashed culture."
            ),
            "checks": [
                "Microscopy — look for rod-shaped bacteria or non-spiral filaments",
                "pH — must stay above 9.5 to suppress bacterial growth",
                "Smell — rotten-egg or sour odour confirms anaerobic bacteria",
                "Recent equipment cleaning or inoculum source",
            ],
            "actions": [
                "Perform microscopy within 1 hour — this is the most important step",
                "If bacteria confirmed: quarantine culture, do not harvest for consumption",
                "Raise pH above 10.0 with NaHCO₃ — bacteriostatic above that threshold",
                "Reduce any organic carbon inputs (CO₂ only, no sugar/molasses)",
                "Consider partial replacement (50 %) with clean inoculum if foam persists 24 h",
            ],
            "critical": True,
        },
        {
            "triggers": ["red", "rouge", "orange", "pink", "rose", "brown", "marron", "reddish"],
            "title": "Colour Change — Carotenoid Stress or Contamination",
            "severity": "WARNING",
            "cause": (
                "Red/orange tints can mean: (1) carotenoid stress response from excess light "
                "or heat, (2) Haematococcus algae contamination, or (3) cell death exposing "
                "background pigments."
            ),
            "checks": [
                "Light intensity — target 5 000–20 000 lux; critical above 30 000",
                "Temperature — critical above 38 °C",
                "Microscopy — spiral filaments (normal) vs round red cells (Haematococcus)",
                "OD680 trend — falling OD + colour change = crash scenario",
            ],
            "actions": [
                "Reduce light intensity if above 25 000 lux",
                "Lower temperature if above 37 °C",
                "Perform microscopy within 1 hour to distinguish stress vs contamination",
                "If Haematococcus confirmed: quarantine, do not harvest",
                "If light/heat stress only: provide 50 % shade for 24 h and reassess",
            ],
            "critical": False,
        },
        {
            "triggers": ["slow", "lent", "not grow", "growth stop", "croissance lente", "stagnant", "no growth"],
            "title": "Slow or Arrested Growth",
            "severity": "WARNING",
            "cause": (
                "Growth slowdown over 2–3 days is usually nutrient limitation (N, P, Fe), "
                "CO₂ deficiency (pH too high), suboptimal temperature, or insufficient light."
            ),
            "checks": [
                "EC — below 2.0 mS/cm suggests nutrient depletion",
                "pH — above 10.5 inhibits growth (CO₂ depleted)",
                "Temperature — below 28 °C or above 38 °C slows metabolism",
                "Turbidity trend over past 5 days",
                "Last full medium refresh date",
            ],
            "actions": [
                "Measure EC first — most common cause of slow growth",
                "If pH > 10.5: increase CO₂ supply or aeration frequency",
                "If temperature out of 30–37 °C range: fix heating/cooling",
                "Consider a 30 % medium exchange if no growth change in 72 h",
                "Check for shading, fouling, or cover obstruction on the pond",
            ],
            "critical": False,
        },
        {
            "triggers": ["crash", "effondrement", "dead", "mort", "smell", "odeur", "black", "noir", "collapsed"],
            "title": "Culture Crash — URGENT",
            "severity": "CRITICAL",
            "cause": (
                "Mass cell death. Likely causes: pH spike above 11, temperature shock, "
                "overwhelming contamination, or total nutrient depletion."
            ),
            "checks": [
                "pH — above 11.0 or below 7.0 is a crash indicator",
                "Smell — ammonia or rotten-egg confirms mass cell death",
                "Visual — transparent or near-black liquid = crash",
                "OD680 if available — below 0.1 is critical",
            ],
            "actions": [
                "DO NOT harvest — crashed culture is not safe for consumption",
                "Take a microscopy sample immediately and document findings",
                "Contact your cultivation specialist or supplier right away",
                "Record all sensor readings and any recent interventions",
                "If pH is still recoverable (8–11): attempt 50 % medium exchange",
                "If strong odour present: assume contamination, plan full restart",
            ],
            "critical": True,
        },
    ]

    matched = next(
        (d for d in DIAGNOSES if any(kw in s for kw in d["triggers"])),
        {
            "title": "Unclassified Symptom",
            "severity": "INFO",
            "cause": "Symptom does not match common patterns — systematic investigation needed.",
            "checks": ["pH", "EC", "Temperature", "Turbidity trend over 5 days", "Microscopy"],
            "actions": [
                "Record all current sensor readings",
                "Take a culture sample for microscopy",
                "Compare today's readings with the 48 h baseline",
                "Document any recent changes (medium, cleaning, environmental)",
            ],
            "critical": False,
        },
    )

    icon = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}.get(matched["severity"], "ℹ️")
    checks_md  = "\n".join(f"- [ ] {c}" for c in matched["checks"])
    actions_md = "\n".join(f"{i+1}. {a}" for i, a in enumerate(matched["actions"]))
    escalate   = (
        "\n\n> 🚨 **ESCALATE** — Contact a cultivation specialist immediately. "
        "Do not attempt to resolve this alone."
    ) if matched.get("critical") else ""

    return f"""{icon} **{matched['severity']} — {matched['title']}**

**Symptom reported:** {symptom_description}

**Root cause:** {matched['cause']}

### Diagnostic checklist
{checks_md}

### Immediate actions
{actions_md}{escalate}
"""


# ── Action Plan Formatter ─────────────────────────────────────────────────────

@tool
def format_action_plan(
    situation_summary: str,
    actions: list,
    check_after_hours: int = 24,
) -> str:
    """Format the agent's final recommendations as a prioritised markdown checklist.

    Call this as the LAST step after all calculations and diagnosis are complete.

    Args:
        situation_summary: One sentence describing the current situation
        actions: Concrete action strings in priority order (3–5 max)
        check_after_hours: When to re-evaluate (hours from now)
    """
    if not actions:
        return f"**No actions required.** Situation: {situation_summary}"

    steps_md = "\n".join(f"- [ ] **Step {i+1}:** {a}" for i, a in enumerate(actions[:5]))

    return f"""## Action Plan

> **Situation:** {situation_summary}

### Steps — execute in order
{steps_md}

### Follow-up
Re-measure sensors in **{check_after_hours} h** and confirm the culture has stabilised.
If readings have not improved, escalate to a cultivation specialist.
"""


# ── Tool registry ─────────────────────────────────────────────────────────────

def get_agent_tools() -> list:
    """Return all tools available to the agentic node."""
    return [
        calculate_ph_correction,
        calculate_ec_correction,
        diagnose_culture_symptom,
        format_action_plan,
    ]
