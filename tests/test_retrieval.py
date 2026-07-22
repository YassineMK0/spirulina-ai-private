"""Retrieval quality test — 10 hand-picked Spirulina queries.

Run (from project root, after ingest):
    .venv\\Scripts\\python tests/test_retrieval.py

For each query the script prints:
  - The query text
  - Top-5 chunks with source, topic, page, score, and a 120-char preview
  - A PASS / WARN line based on the best score threshold

Pass criterion:
  Best chunk score < 1.5   (L2 distance; lower = more similar)
  If the collection is empty the whole suite is skipped with a clear message.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.retriever.retrieve import retrieve, format_context

# ---------------------------------------------------------------------------
# 10 test queries covering all 4 topics
# ---------------------------------------------------------------------------

QUERIES: list[dict] = [
    # --- scientific_literature (papers) ---
    {
        "query": "What is the optimal pH range for Spirulina platensis cultivation?",
        "topic_hint": "scientific_literature",
        "note":  "Core biology — should appear in most papers",
    },
    {
        "query": "Effect of light intensity on spirulina biomass productivity",
        "topic_hint": "scientific_literature",
        "note":  "Photosynthesis / growth rate literature",
    },
    {
        "query": "Nitrogen and phosphorus requirements for spirulina growth medium",
        "topic_hint": "scientific_literature",
        "note":  "Nutrient chemistry topic",
    },
    # --- cultivation_manual ---
    {
        "query": "How to prepare Zarrouk medium for spirulina culture",
        "topic_hint": "cultivation_manual",
        "note":  "Standard cultivation recipe",
    },
    {
        "query": "Daily monitoring routine for spirulina open raceway pond",
        "topic_hint": "cultivation_manual",
        "note":  "Operational procedure",
    },
    {
        "query": "Harvest frequency and filtration method for spirulina",
        "topic_hint": "cultivation_manual",
        "note":  "Post-production step",
    },
    # --- troubleshooting ---
    {
        "query": "Why is the pH rising sharply in my spirulina culture?",
        "topic_hint": "troubleshooting",
        "note":  "pH instability scenario",
    },
    {
        "query": "How to detect and treat contamination in spirulina pond",
        "topic_hint": "troubleshooting",
        "note":  "Contamination scenario",
    },
    # --- qa_pairs ---
    {
        "query": "What EC conductivity level is normal for spirulina?",
        "topic_hint": "qa_pairs",
        "note":  "EC drift — common operator question",
    },
    {
        "query": "When should I harvest spirulina based on OD measurements?",
        "topic_hint": "qa_pairs",
        "note":  "Harvest readiness question",
    },
]

# L2 distance below this is considered a good match
SCORE_THRESHOLD = 1.5

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    # Quick sanity: can we connect at all?
    try:
        sample = retrieve("spirulina", top_k=1)
    except Exception as exc:
        print(f"ERROR: Could not connect to ChromaDB: {exc}")
        print("Run the ingest script first:  .venv313/Scripts/python -m rag.embedder.ingest")
        sys.exit(1)

    if not sample:
        print("Collection is empty — run ingest first.")
        print("  .venv313/Scripts/python -m rag.embedder.ingest")
        sys.exit(0)

    passed = 0
    warned = 0

    print("=" * 70)
    print("SPIRULINA RAG RETRIEVAL TEST  (top_k=5, model=multilingual-MiniLM)")
    print("=" * 70)

    for i, case in enumerate(QUERIES, start=1):
        query      = case["query"]
        topic_hint = case["topic_hint"]
        note       = case["note"]

        chunks = retrieve(query, top_k=5)
        best_score = chunks[0]["score"] if chunks else 999.0

        status = "PASS" if best_score < SCORE_THRESHOLD else "WARN"
        if status == "PASS":
            passed += 1
        else:
            warned += 1

        print(f"\n[{i:02d}] {status}  best_score={best_score:.4f}  (threshold<{SCORE_THRESHOLD})")
        print(f"     Query : {query}")
        print(f"     Note  : {note}  [expected topic: {topic_hint}]")
        print(f"     Top-5 results:")

        for rank, c in enumerate(chunks, start=1):
            preview = c["text"].replace("\n", " ")[:120]
            topic_match = "*" if c["topic"] == topic_hint else " "
            print(
                f"       {rank}. [{topic_match}topic={c['topic']:<24}] "
                f"src={c['source']:<30} p={c['page']:<3} score={c['score']:.4f}"
            )
            print(f"          \"{preview}\"")

    print()
    print("=" * 70)
    print(f"Results: {passed} PASS / {warned} WARN  out of {len(QUERIES)} queries")
    print()
    if warned > 0:
        print("WARN means best score >= 1.5 — likely the relevant KB files are not")
        print("yet ingested for that topic. Add files to data/raw/ and re-run ingest.")
    else:
        print("All queries returned relevant results within the score threshold.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Topic-filtered spot checks (bonus)
# ---------------------------------------------------------------------------

def run_filter_checks() -> None:
    """Verify that topic filters actually restrict results."""
    print("\n--- Metadata filter spot checks ---")
    for topic in ("scientific_literature", "cultivation_manual", "qa_pairs", "troubleshooting"):
        chunks = retrieve("spirulina", top_k=3, topic=topic)
        wrong = [c for c in chunks if c["topic"] != topic]
        status = "PASS" if not wrong else f"FAIL ({len(wrong)} wrong-topic chunks)"
        print(f"  filter topic={topic:<24} -> {len(chunks)} chunks  [{status}]")


if __name__ == "__main__":
    run_tests()
    run_filter_checks()
