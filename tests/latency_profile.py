"""Latency profiler for the SpirulinaAI RAG pipeline.

Measures time for each stage: embedding, ChromaDB search, BM25, LLM call,
formatting. Runs 5 questions and reports per-stage breakdown + totals.

Target: < 3 seconds end-to-end for RAG responses.

Run:
    .venv\\Scripts\\python -m tests.latency_profile
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

QUESTIONS = [
    "What is the optimal pH for spirulina?",
    "My culture is turning yellow, what should I do?",
    "When should I harvest based on OD680?",
    "How do I raise the pH if it drops too low?",
    "What nutrients does spirulina need to grow?",
]


def _t():
    return time.perf_counter()


def profile_retrieval(question: str) -> dict:
    """Time each step inside the retrieval pipeline."""
    from chromadb import PersistentClient
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    import os

    chroma_dir  = os.getenv("CHROMA_PERSIST_DIR", "./data/processed/chroma")
    embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
    collection_name = "spirulina_kb"

    timings = {}

    # 1. Embedding
    t0 = _t()
    ef = SentenceTransformerEmbeddingFunction(model_name=embed_model)
    query_vec = ef([question])
    timings["embedding_ms"] = round((_t() - t0) * 1000, 1)

    # 2. ChromaDB vector search
    t0 = _t()
    client = PersistentClient(path=chroma_dir)
    collection = client.get_collection(name=collection_name, embedding_function=ef)
    dense_results = collection.query(query_embeddings=query_vec, n_results=8)
    timings["chromadb_ms"] = round((_t() - t0) * 1000, 1)

    # 3. BM25 index + search
    t0 = _t()
    from rank_bm25 import BM25Okapi
    all_docs = collection.get(include=["documents"])
    corpus = [d.split() for d in all_docs["documents"]]
    bm25 = BM25Okapi(corpus)
    bm25.get_scores(question.split())
    timings["bm25_ms"] = round((_t() - t0) * 1000, 1)

    # Combined retrieval (using our actual retrieve function)
    t0 = _t()
    from rag.retriever.retrieve import retrieve
    context = retrieve(question, top_k=8)
    timings["total_retrieval_ms"] = round((_t() - t0) * 1000, 1)

    context_str = "\n\n".join(c["text"] for c in context) if isinstance(context, list) and context and isinstance(context[0], dict) else str(context)
    timings["context_chars"] = len(context_str)

    return timings, context_str


def profile_generation(question: str, context: str) -> dict:
    """Time LLM generation."""
    from rag.generator.generate import generate_answer

    timings = {}

    t0 = _t()
    response = generate_answer(question=question, context=context, history=[])
    timings["llm_ms"] = round((_t() - t0) * 1000, 1)
    timings["response_chars"] = len(response)

    return timings, response


def profile_formatting(response: str) -> dict:
    """Time response formatting."""
    from agent.formatter import format_message

    timings = {}
    t0 = _t()
    format_message(
        raw_answer=response, intent="KNOWLEDGE", has_container=False,
        rag_context="", sensor={}, ml_outputs={}, container_id="",
    )
    timings["format_ms"] = round((_t() - t0) * 1000, 1)

    return timings


def run():
    print("\nSpirulinaAI Latency Profiler")
    print("=" * 65)
    print(f"{'Stage':<28} {'Q1':>6} {'Q2':>6} {'Q3':>6} {'Q4':>6} {'Q5':>6} {'AVG':>7}")
    print("-" * 65)

    all_timings = []

    for i, q in enumerate(QUESTIONS, 1):
        t_total = _t()
        r_timings, context_str = profile_retrieval(q)
        g_timings, response    = profile_generation(q, context_str)
        f_timings              = profile_formatting(response)
        total_ms = round((_t() - t_total) * 1000, 1)

        all_timings.append({
            **r_timings,
            **g_timings,
            **f_timings,
            "total_ms": total_ms,
        })

    # Print per-stage averages
    stages = [
        ("Embedding",          "embedding_ms"),
        ("ChromaDB search",    "chromadb_ms"),
        ("BM25 search",        "bm25_ms"),
        ("Total retrieval",    "total_retrieval_ms"),
        ("LLM generation",     "llm_ms"),
        ("Formatting",         "format_ms"),
        ("TOTAL end-to-end",   "total_ms"),
    ]

    for label, key in stages:
        vals = [t.get(key, 0) for t in all_timings]
        avg  = round(sum(vals) / len(vals), 1)
        row  = f"  {label:<26}"
        for v in vals:
            row += f" {v:>6.0f}"
        row += f" {avg:>7.0f}"
        if key == "total_ms":
            status = "OK" if avg < 3000 else "SLOW"
            row += f"  [{status}]"
        print(row)

    print("-" * 65)
    avg_total = round(sum(t["total_ms"] for t in all_timings) / len(all_timings))
    print(f"\n  Average end-to-end: {avg_total} ms  (target: < 3000 ms)")

    # Identify bottleneck
    stage_avgs = {key: round(sum(t.get(key, 0) for t in all_timings) / len(all_timings)) for _, key in stages[:-1]}
    bottleneck_key = max(stage_avgs, key=stage_avgs.get)
    bottleneck_label = next(l for l, k in stages if k == bottleneck_key)
    bottleneck_pct = round(stage_avgs[bottleneck_key] / avg_total * 100)
    print(f"  Bottleneck: {bottleneck_label} ({stage_avgs[bottleneck_key]} ms, {bottleneck_pct}% of total)")

    if avg_total > 3000:
        print("\n  Optimization suggestions:")
        if stage_avgs["embedding_ms"] > 500:
            print("  - Embedding slow: consider caching query embeddings for frequent questions")
        if stage_avgs["bm25_ms"] > 500:
            print("  - BM25 slow: index is rebuilt per call — caching is already in retrieve.py but check _get_bm25_index()")
        if stage_avgs["llm_ms"] > 2000:
            print("  - LLM is the bottleneck (expected for API calls) — reduce max_tokens or switch to 8b model for simple queries")
        if stage_avgs["chromadb_ms"] > 300:
            print("  - ChromaDB slow: reduce top_k from 8 to 5")
    else:
        print("  Target met.")

    print()


if __name__ == "__main__":
    run()
