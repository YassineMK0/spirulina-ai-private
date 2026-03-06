"""Retrieval evaluation set — 20 query / keyword pairs.

A query is a "hit" if AT LEAST ONE of the top-k retrieved chunks contains
ALL keywords in the `must` list (case-insensitive substring match).

The `any_of` list is optional: if provided, the chunk must also contain
at least one term from that list (useful for synonyms).

Topics are distributed across all 4 KB categories (5 per topic).
"""

from __future__ import annotations

# Each entry:
#   query    : str         - natural-language question posed to the retriever
#   must     : list[str]  - ALL of these must appear in a matching chunk
#   any_of   : list[str]  - at least ONE must appear ([] = no constraint)
#   topic    : str         - expected source topic (informational, not enforced)
#   note     : str         - human-readable description of the test case

EVAL_SET: list[dict] = [

    # -----------------------------------------------------------------------
    # scientific_literature  (queries 1-5)
    # -----------------------------------------------------------------------
    {
        "query":  "What is the optimal pH range for Spirulina platensis cultivation?",
        "must":   ["pH", "spirulina"],
        "any_of": ["8", "9", "10", "alkaline", "optimal"],
        "topic":  "scientific_literature",
        "note":   "Core cultivation parameter — should be in every paper",
    },
    {
        "query":  "How does light intensity affect spirulina biomass productivity?",
        "must":   ["light", "biomass"],
        "any_of": ["productiv", "growth", "photosynthes", "lux", "µmol"],
        "topic":  "scientific_literature",
        "note":   "Photobiology — standard research topic",
    },
    {
        "query":  "What temperature range is optimal for Spirulina platensis?",
        "must":   ["temperature", "spirulina"],
        "any_of": ["35", "37", "38", "°C", "optimal", "growth"],
        "topic":  "scientific_literature",
        "note":   "Thermophilic optimum around 35-37 C",
    },
    {
        "query":  "Nitrogen and bicarbonate requirements for spirulina culture medium",
        "must":   ["nitrogen"],
        "any_of": ["NaHCO3", "bicarbonate", "NH4", "urea", "medium", "Zarrouk"],
        "topic":  "scientific_literature",
        "note":   "Nutrient chemistry in growth medium",
    },
    {
        "query":  "Protein content and amino acid profile of Spirulina platensis",
        "must":   ["protein", "spirulina"],
        "any_of": ["amino", "essential", "%", "nutritional", "composition"],
        "topic":  "scientific_literature",
        "note":   "Spirulina nutritional value — high protein ~60-70%",
    },

    # -----------------------------------------------------------------------
    # cultivation_manual  (queries 6-10)
    # -----------------------------------------------------------------------
    {
        "query":  "How to prepare Zarrouk medium for spirulina cultivation",
        "must":   ["Zarrouk"],
        "any_of": ["NaHCO3", "medium", "prepar", "recipe", "formula", "g/L"],
        "topic":  "cultivation_manual",
        "note":   "Standard Zarrouk recipe — should be in manuals",
    },
    {
        "query":  "Daily monitoring routine for pH, EC, and temperature in spirulina pond",
        "must":   ["pH", "EC"],
        "any_of": ["monitor", "daily", "routine", "measur", "temperature", "check"],
        "topic":  "cultivation_manual",
        "note":   "Operational SOP for daily checks",
    },
    {
        "query":  "Spirulina harvest filtration and drying procedure",
        "must":   ["harvest"],
        "any_of": ["filter", "drying", "dry", "mesh", "centrifug", "sun", "spray"],
        "topic":  "cultivation_manual",
        "note":   "Post-production processing steps",
    },
    {
        "query":  "How to inoculate a new spirulina culture from starter stock",
        "must":   ["inoculat"],
        "any_of": ["starter", "stock", "ratio", "culture", "seed", "volume"],
        "topic":  "cultivation_manual",
        "note":   "Culture initiation procedure",
    },
    {
        "query":  "Open raceway pond design and dimensions for spirulina production",
        "must":   ["raceway"],
        "any_of": ["pond", "paddle", "channel", "design", "dimension", "depth", "cm"],
        "topic":  "cultivation_manual",
        "note":   "Infrastructure specifications",
    },

    # -----------------------------------------------------------------------
    # troubleshooting  (queries 11-15)
    # -----------------------------------------------------------------------
    {
        "query":  "Why is pH rising sharply in my spirulina culture and how to fix it?",
        "must":   ["pH"],
        "any_of": ["rise", "high", "sharp", "CO2", "carbon", "HCl", "acid", "fix"],
        "topic":  "troubleshooting",
        "note":   "pH instability — most common operator issue",
    },
    {
        "query":  "Electrical conductivity EC drift causes and correction in spirulina",
        "must":   ["EC"],
        "any_of": ["conductivity", "drift", "salinity", "evaporat", "dilut", "mS"],
        "topic":  "troubleshooting",
        "note":   "EC drift from evaporation or over-feeding",
    },
    {
        "query":  "How to detect and treat contamination in spirulina culture",
        "must":   ["contaminat"],
        "any_of": ["algae", "bacteria", "protozoa", "green", "detect", "microscop"],
        "topic":  "troubleshooting",
        "note":   "Contamination identification and remediation",
    },
    {
        "query":  "Spirulina culture low productivity due to poor light management",
        "must":   ["light"],
        "any_of": ["productiv", "low", "shading", "turbid", "depth", "mixing"],
        "topic":  "troubleshooting",
        "note":   "Light limitation causing poor growth",
    },
    {
        "query":  "Spirulina culture crash signs and emergency recovery steps",
        "must":   ["spirulina"],
        "any_of": ["crash", "death", "die", "recover", "emergency", "color", "yellow"],
        "topic":  "troubleshooting",
        "note":   "Culture death / crash scenario",
    },

    # -----------------------------------------------------------------------
    # qa_pairs  (queries 16-20)
    # -----------------------------------------------------------------------
    {
        "query":  "What is the normal electrical conductivity EC value for spirulina medium?",
        "must":   ["EC"],
        "any_of": ["mS", "conductivity", "normal", "range", "value", "optimal"],
        "topic":  "qa_pairs",
        "note":   "FAQ: expected EC reading",
    },
    {
        "query":  "When should I harvest spirulina based on optical density OD measurements?",
        "must":   ["harvest"],
        "any_of": ["OD", "optical density", "absorbance", "nm", "density", "when"],
        "topic":  "qa_pairs",
        "note":   "FAQ: harvest trigger based on OD",
    },
    {
        "query":  "How often should nutrients be added to the spirulina culture?",
        "must":   ["nutrient"],
        "any_of": ["add", "frequency", "often", "feed", "replenish", "schedule"],
        "topic":  "qa_pairs",
        "note":   "FAQ: nutrient replenishment frequency",
    },
    {
        "query":  "What causes yellow or pale color in spirulina culture?",
        "must":   ["color"],
        "any_of": ["yellow", "pale", "chlorophyll", "phycocyanin", "bleach", "light"],
        "topic":  "qa_pairs",
        "note":   "FAQ: discoloration diagnosis",
    },
    {
        "query":  "How does CO2 supplementation improve spirulina growth rate?",
        "must":   ["CO2"],
        "any_of": ["growth", "carbon", "supplementat", "inject", "pH", "productiv"],
        "topic":  "qa_pairs",
        "note":   "FAQ: CO2 enrichment effect",
    },
]
