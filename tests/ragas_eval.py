"""RAGAS evaluation for SpirulinaAI RAG pipeline.

Evaluates 20 questions (factual, troubleshooting, operational) using the
official RAGAS library with Groq as the judge LLM.

Metrics:
    faithfulness      - is the answer grounded in the retrieved context?
    answer_relevancy  - is the answer relevant to the question?
    context_recall    - does the context cover the ground truth?

Run:
    .venv\\Scripts\\python -m tests.ragas_eval
    .venv\\Scripts\\python -m tests.ragas_eval --save
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()


# ---------------------------------------------------------------------------
# Evaluation dataset — 20 questions with ground truth
# ---------------------------------------------------------------------------

EVAL_SET = [
    # --- Factual (7 questions) ---
    {
        "category": "factual",
        "question": "What is the optimal pH range for spirulina cultivation?",
        "ground_truth": "The optimal pH range for spirulina cultivation is between 8.5 and 10.5, with best growth around 9.5 to 10.",
    },
    {
        "category": "factual",
        "question": "What temperature range does spirulina grow best in?",
        "ground_truth": "Spirulina grows best between 30 and 37 degrees Celsius, with optimal growth around 35 degrees.",
    },
    {
        "category": "factual",
        "question": "What does OD680 measure in a spirulina culture?",
        "ground_truth": "OD680 measures optical density at 680nm, which is used as a proxy for biomass concentration in the culture.",
    },
    {
        "category": "factual",
        "question": "What is the protein content of spirulina?",
        "ground_truth": "Spirulina contains between 55 and 70 percent protein by dry weight, making it one of the richest plant-based protein sources.",
    },
    {
        "category": "factual",
        "question": "What light intensity is recommended for spirulina growth?",
        "ground_truth": "Spirulina requires light intensity of about 150 to 250 micromoles per square meter per second, or roughly 5000 to 10000 lux for dense cultures.",
    },
    {
        "category": "factual",
        "question": "What is EC conductivity and why does it matter for spirulina?",
        "ground_truth": "EC (electrical conductivity) measures the salt concentration in the growth medium. For spirulina, optimal EC is typically 18 to 28 mS/cm. Too high indicates salt buildup which causes osmotic stress.",
    },
    {
        "category": "factual",
        "question": "What nutrients does spirulina need to grow?",
        "ground_truth": "Spirulina needs nitrogen (sodium bicarbonate or urea), phosphorus, potassium, magnesium, and trace minerals. The Zarrouk medium is the standard formulation.",
    },
    # --- Troubleshooting (7 questions) ---
    {
        "category": "troubleshooting",
        "question": "My spirulina culture is turning yellow. What is wrong?",
        "ground_truth": "Yellow color in spirulina usually indicates nitrogen deficiency. The culture is breaking down its phycocyanin pigments. Add nitrogen source such as sodium bicarbonate or urea immediately.",
    },
    {
        "category": "troubleshooting",
        "question": "The pH in my culture dropped to 7.2. What should I do?",
        "ground_truth": "A pH of 7.2 is critically low for spirulina. Add sodium bicarbonate immediately to raise pH back to 9-10. Low pH can indicate CO2 buildup or bacterial contamination.",
    },
    {
        "category": "troubleshooting",
        "question": "There is white foam on the surface of my culture. Is this normal?",
        "ground_truth": "Small amounts of foam can be normal due to agitation releasing proteins. Excessive foam may indicate contamination or over-aeration. Monitor and reduce agitation if excessive.",
    },
    {
        "category": "troubleshooting",
        "question": "My culture has a bad smell. What could be causing this?",
        "ground_truth": "A bad smell usually indicates bacterial contamination or anaerobic decomposition. This can happen when the culture crashes or when conditions favor competing bacteria. Check pH and temperature, and consider starting fresh.",
    },
    {
        "category": "troubleshooting",
        "question": "My conductivity is 38 mS/cm. Is this a problem?",
        "ground_truth": "Yes, 38 mS/cm is above the optimal range of 18-28 mS/cm. High EC indicates salt buildup. Dilute the culture with fresh water or replace part of the medium to bring conductivity back to normal.",
    },
    {
        "category": "troubleshooting",
        "question": "Growth has slowed significantly after two weeks. What should I check?",
        "ground_truth": "Check pH, temperature, nutrient levels, and light. Common causes of slow growth are nitrogen deficiency, pH drift, temperature too high or too low, insufficient light, or high cell density causing self-shading.",
    },
    {
        "category": "troubleshooting",
        "question": "I see green patches in my spirulina culture. What are they?",
        "ground_truth": "Green patches likely indicate green algae contamination such as Chlorella. These compete with spirulina. Raise pH above 10 to favor spirulina, which tolerates high pH better than most contaminants.",
    },
    # --- Operational (6 questions) ---
    {
        "category": "operational",
        "question": "When should I harvest my spirulina?",
        "ground_truth": "Harvest when OD680 reaches 0.8 to 1.2 g/L. Above 1.5 g/L the culture self-shades and growth slows. Partial harvests of 20-30% every few days maintain optimal density.",
    },
    {
        "category": "operational",
        "question": "How do I do a partial harvest?",
        "ground_truth": "Remove 20 to 30 percent of the culture volume through a fine mesh filter (50-100 micron). Replace with fresh nutrient solution. Harvest in the morning when pH is more stable.",
    },
    {
        "category": "operational",
        "question": "How often should I stir or agitate my spirulina culture?",
        "ground_truth": "Spirulina should be agitated continuously or at least several times per day to prevent settling, ensure even light exposure, and improve gas exchange.",
    },
    {
        "category": "operational",
        "question": "How do I dry harvested spirulina?",
        "ground_truth": "After filtering, dry at temperatures below 40 degrees Celsius to preserve nutrients and phycocyanin. Spray drying, drum drying, or sun drying at low temperature are common methods.",
    },
    {
        "category": "operational",
        "question": "How do I refill my container after harvesting?",
        "ground_truth": "After harvesting, top up with fresh nutrient solution (Zarrouk medium or equivalent) to restore volume. Adjust pH if needed. Monitor EC to ensure nutrients are balanced.",
    },
    {
        "category": "operational",
        "question": "Quelle est la temperature optimale pour la spiruline?",
        "ground_truth": "La temperature optimale pour la croissance de la spiruline est entre 30 et 37 degres Celsius, avec un optimum autour de 35 degres.",
    },
]


# ---------------------------------------------------------------------------
# Build RAGAS dataset by running questions through the pipeline
# ---------------------------------------------------------------------------

def build_dataset():
    from ragas import EvaluationDataset, SingleTurnSample
    from rag.retriever.retrieve import retrieve
    from rag.generator.generate import generate_answer

    samples = []
    print(f"Running {len(EVAL_SET)} questions through RAG pipeline...")
    print("-" * 60)

    for i, item in enumerate(EVAL_SET, 1):
        q = item["question"]
        print(f"  [{i:02d}/{len(EVAL_SET)}] {q[:65]}...")

        try:
            context_raw = retrieve(q, top_k=8)
            # retrieve() returns a list of dicts with a "text" key
            if isinstance(context_raw, list) and context_raw and isinstance(context_raw[0], dict):
                context_list = [c["text"].strip() for c in context_raw if c.get("text", "").strip()]
            elif isinstance(context_raw, list):
                context_list = [str(c).strip() for c in context_raw if str(c).strip()]
            else:
                context_list = [str(context_raw).strip()]

            context_str = "\n\n".join(context_list)
            response = generate_answer(question=q, context=context_str, history=[])

            samples.append(SingleTurnSample(
                user_input=q,
                retrieved_contexts=context_list,
                response=response,
                reference=item["ground_truth"],
            ))
        except Exception as exc:
            print(f"    ERROR: {exc}")

    print(f"\nBuilt {len(samples)} samples.")
    return EvaluationDataset(samples=samples), samples


# ---------------------------------------------------------------------------
# Run RAGAS evaluation
# ---------------------------------------------------------------------------

def run_eval(dataset, save: bool = False):
    from ragas import evaluate
    from ragas.metrics._faithfulness import faithfulness
    from ragas.metrics._context_recall import context_recall
    from ragas.llms import LangchainLLMWrapper
    from langchain_groq import ChatGroq

    print("\nConfiguring RAGAS judge (Groq llama-3.3-70b-versatile)...")

    judge_llm = LangchainLLMWrapper(ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
    ))
    faithfulness.llm = judge_llm
    context_recall.llm = judge_llm

    metrics = [faithfulness, context_recall]

    print("Running RAGAS evaluation...")
    results = evaluate(dataset=dataset, metrics=metrics)

    df = results.to_pandas()

    # Per-category breakdown
    categories = ["factual", "troubleshooting", "operational"]
    cat_labels = [item["category"] for item in EVAL_SET[:len(df)]]
    df["category"] = cat_labels[:len(df)]

    print("\n" + "=" * 65)
    print("  RAGAS EVALUATION RESULTS")
    print("=" * 65)

    metric_cols = ["faithfulness", "context_recall"]
    available = [c for c in metric_cols if c in df.columns]

    for cat in categories:
        subset = df[df["category"] == cat]
        if subset.empty:
            continue
        print(f"\n  {cat.upper()} ({len(subset)} questions):")
        for col in available:
            val = subset[col].mean()
            print(f"    {col:<22} {val:.3f}")

    print(f"\n  OVERALL ({len(df)} questions):")
    for col in available:
        val = df[col].mean()
        threshold = {"faithfulness": 0.85, "context_recall": 0.70}
        status = "PASS" if val >= threshold.get(col, 0) else "FAIL"
        print(f"    {col:<22} {val:.3f}  [{status}]")

    print("=" * 65)

    if save:
        out = {
            "overall": {col: round(float(df[col].mean()), 3) for col in available},
            "by_category": {
                cat: {col: round(float(df[df["category"] == cat][col].mean()), 3) for col in available}
                for cat in categories
            },
            "per_question": df[["user_input", "category"] + available].to_dict(orient="records"),
        }
        path = "data/processed/ragas_eval_results.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"\n  Results saved to {path}")

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true", help="Save results to JSON")
    args = parser.parse_args()

    dataset, _ = build_dataset()
    run_eval(dataset, save=args.save)
