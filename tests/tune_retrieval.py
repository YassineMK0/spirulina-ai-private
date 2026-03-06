"""Retrieval tuning script — grid search over chunk_size x top_k x filter.

What it does
------------
1. For each chunk_size in [300, 500, 800]:
   - Ingests data/raw/ into a separate collection  spirulina_kb_<size>
     (skips re-ingestion if collection already exists and is non-empty)
2. For each (chunk_size, top_k, use_filter) combination:
   - Runs all 20 eval queries from tests/eval_set.py
   - Counts hits  (a hit = at least one top-k chunk contains ALL must-keywords
                   AND at least one any_of keyword if any_of is non-empty)
3. Prints a ranked results table
4. Prints the winning config (first one to exceed 80 % hit rate)

Run (from project root):
    .venv\\Scripts\\python tests/tune_retrieval.py

The script is slow on first run (embeds 3x your corpus). Subsequent runs
reuse cached collections and are fast.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from rag.embedder.ingest import (
    CHROMA_DIR,
    EMBED_MODEL,
    RAW_DIR,
    ingest,
)
from tests.eval_set import EVAL_SET

# ---------------------------------------------------------------------------
# Grid parameters
# ---------------------------------------------------------------------------

CHUNK_SIZES  = [300, 500, 800]
CHUNK_OVERLAP_RATIO = 0.10   # overlap = chunk_size * ratio  (keeps ratio consistent)
TOP_K_VALUES = [3, 5, 8]
USE_FILTERS  = [False, True]  # True = restrict query to expected topic

TARGET_HIT_RATE = 0.80        # stop search once this is reached


# ---------------------------------------------------------------------------
# Hit detection
# ---------------------------------------------------------------------------

def _is_chunk_hit(text: str, must: list[str], any_of: list[str]) -> bool:
    """True if chunk satisfies the must + any_of keyword constraints."""
    tl = text.lower()
    if not all(kw.lower() in tl for kw in must):
        return False
    if any_of and not any(kw.lower() in tl for kw in any_of):
        return False
    return True


def _query_hits(
    collection,
    query: str,
    top_k: int,
    must: list[str],
    any_of: list[str],
    topic_filter: str | None,
) -> bool:
    """Return True if any of the top-k chunks is a hit for this eval case."""
    total = collection.count()
    if total == 0:
        return False

    kwargs: dict = dict(
        query_texts=[query],
        n_results=min(top_k, total),
        include=["documents", "metadatas"],
    )
    if topic_filter:
        kwargs["where"] = {"topic": topic_filter}

    try:
        results = collection.query(**kwargs)
    except Exception:
        return False

    for text in results["documents"][0]:
        if _is_chunk_hit(text, must, any_of):
            return True
    return False


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def _collection_name(chunk_size: int) -> str:
    return f"spirulina_kb_{chunk_size}"


def _get_or_create_collection(client, name: str):
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client.get_or_create_collection(name=name, embedding_function=ef)


def _ensure_ingested(chunk_size: int, client) -> int:
    """Ingest data/raw/ into spirulina_kb_<chunk_size> if not already done."""
    name = _collection_name(chunk_size)
    col  = _get_or_create_collection(client, name)

    if col.count() > 0:
        print(f"  [cache] {name}  ({col.count()} chunks already ingested)")
        return col.count()

    overlap = max(30, int(chunk_size * CHUNK_OVERLAP_RATIO))
    print(f"  [ingest] chunk_size={chunk_size}  overlap={overlap}  -> {name}")
    t0 = time.time()
    n = ingest(
        raw_dir=RAW_DIR,
        chroma_dir=CHROMA_DIR,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        collection_name=name,
        verbose=False,
    )
    print(f"           {n} chunks  ({time.time()-t0:.1f}s)")
    return n


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class Result:
    chunk_size:  int
    top_k:       int
    use_filter:  bool
    hits:        int
    total:       int
    duration_s:  float
    hit_rate:    float = field(init=False)

    def __post_init__(self):
        self.hit_rate = self.hits / self.total if self.total else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_grid() -> None:
    # Verify data/raw/ has files
    raw_files = [
        p for p in RAW_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".json", ".md", ".txt"}
    ]
    if not raw_files:
        print("ERROR: No source files found in data/raw/")
        print("  Add your KB files first, then re-run.")
        sys.exit(1)

    print("=" * 70)
    print("SPIRULINA RAG RETRIEVAL TUNING")
    print(f"  Eval set  : {len(EVAL_SET)} queries")
    print(f"  Chunk sizes tested : {CHUNK_SIZES}")
    print(f"  Top-k values       : {TOP_K_VALUES}")
    print(f"  Metadata filter    : {USE_FILTERS}")
    print(f"  Target hit rate    : {TARGET_HIT_RATE*100:.0f}%")
    print("=" * 70)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # --- Phase 1: ensure all collections are ingested ---
    print("\n[Phase 1] Ensuring collections are ingested...")
    chunk_counts: dict[int, int] = {}
    for cs in CHUNK_SIZES:
        n = _ensure_ingested(cs, client)
        chunk_counts[cs] = n
        if n == 0:
            print(f"  [warn] chunk_size={cs} produced 0 chunks — skipping in eval")

    # --- Phase 2: grid evaluation ---
    print("\n[Phase 2] Running eval grid...")
    results: list[Result] = []

    for cs in CHUNK_SIZES:
        if chunk_counts.get(cs, 0) == 0:
            continue
        col_name = _collection_name(cs)
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        col = client.get_collection(name=col_name, embedding_function=ef)

        for top_k in TOP_K_VALUES:
            for use_filter in USE_FILTERS:
                hits = 0
                t0 = time.time()

                for case in EVAL_SET:
                    topic_filter = case["topic"] if use_filter else None
                    got_hit = _query_hits(
                        collection=col,
                        query=case["query"],
                        top_k=top_k,
                        must=case["must"],
                        any_of=case.get("any_of", []),
                        topic_filter=topic_filter,
                    )
                    if got_hit:
                        hits += 1

                r = Result(
                    chunk_size=cs,
                    top_k=top_k,
                    use_filter=use_filter,
                    hits=hits,
                    total=len(EVAL_SET),
                    duration_s=time.time() - t0,
                )
                results.append(r)
                filter_tag = "filtered" if use_filter else "unfiltered"
                bar = "#" * hits + "." * (len(EVAL_SET) - hits)
                print(
                    f"  cs={cs:>3}  top_k={top_k}  {filter_tag:<10}  "
                    f"hits={hits:>2}/{len(EVAL_SET)}  [{bar}]  {r.hit_rate*100:.0f}%"
                )

    # --- Phase 3: ranked table ---
    results.sort(key=lambda r: (-r.hit_rate, r.top_k, r.chunk_size))

    print()
    print("=" * 70)
    print("RESULTS  (sorted by hit rate, then top_k asc, chunk_size asc)")
    print("=" * 70)
    print(f"{'Rank':<5} {'chunk_size':<12} {'top_k':<7} {'filter':<11} {'hits':<9} {'hit_rate':<10} {'time'}")
    print("-" * 70)
    winner: Result | None = None
    for rank, r in enumerate(results, start=1):
        flag = " <-- WINNER" if winner is None and r.hit_rate >= TARGET_HIT_RATE else ""
        if flag:
            winner = r
        print(
            f"{rank:<5} {r.chunk_size:<12} {r.top_k:<7} "
            f"{'yes' if r.use_filter else 'no':<11} "
            f"{r.hits}/{r.total:<5}   {r.hit_rate*100:>5.1f}%    "
            f"{r.duration_s:.1f}s{flag}"
        )

    print()
    if winner:
        print("WINNING CONFIG (first config >= 80% hit rate):")
        print(f"  chunk_size   = {winner.chunk_size}")
        print(f"  chunk_overlap= {max(30, int(winner.chunk_size * CHUNK_OVERLAP_RATIO))}")
        print(f"  top_k        = {winner.top_k}")
        print(f"  topic_filter = {winner.use_filter}")
        print(f"  hit_rate     = {winner.hit_rate*100:.1f}%  ({winner.hits}/{winner.total})")
        print()
        print("To apply: update CHUNK_SIZE / CHUNK_OVERLAP in rag/embedder/ingest.py")
        print("and DEFAULT_TOP_K in rag/retriever/retrieve.py, then re-run ingest.")
    else:
        best = results[0] if results else None
        if best:
            print(f"No config reached {TARGET_HIT_RATE*100:.0f}%. Best was {best.hit_rate*100:.1f}% "
                  f"(cs={best.chunk_size}, top_k={best.top_k}).")
            print("Suggestions:")
            print("  - Add more KB files to data/raw/ and re-run")
            print("  - Review eval_set.py keywords — they may not match your actual docs")
            print("  - Increase top_k beyond 8")
        else:
            print("No results — all collections were empty.")
    print("=" * 70)


if __name__ == "__main__":
    run_grid()
