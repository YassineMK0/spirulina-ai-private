"""Hybrid retriever — BM25 + dense (ChromaDB) fused with Reciprocal Rank Fusion.

Usage:
    from rag.retriever.retrieve import retrieve, format_context

    # Basic retrieval (hybrid by default)
    chunks = retrieve("What is the optimal pH for spirulina?", top_k=5)

    # Filter by topic
    chunks = retrieve("pH instability causes", top_k=5, topic="troubleshooting")
    chunks = retrieve("biomass productivity", top_k=5, topic="scientific_literature")

    # Dense-only (skip BM25)
    chunks = retrieve("...", top_k=5, use_hybrid=False)

    # Format for LLM context
    context = format_context(chunks)

Valid topic values:
    scientific_literature | cultivation_manual | qa_pairs | troubleshooting

How hybrid works:
    1. Dense:  ChromaDB queries the embedding index -> top (top_k*2) results ranked by L2
    2. BM25:   Keyword index built from all corpus chunks -> top (top_k*2) by BM25 score
    3. RRF:    score(chunk) = 1/(RRF_K + dense_rank) + 1/(RRF_K + bm25_rank)
               Chunks that rank well in BOTH lists bubble to the top.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_DIR      = Path(os.getenv("CHROMA_PERSIST_DIR", "data/processed/chroma"))
COLLECTION_NAME = "spirulina_kb"
EMBED_MODEL     = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_TOP_K   = 5
RRF_K           = 60   # RRF constant — higher = smoother rank blending

VALID_TOPICS = {
    "scientific_literature",
    "cultivation_manual",
    "qa_pairs",
    "troubleshooting",
}


# ---------------------------------------------------------------------------
# Lazy singletons — loaded once, reused on every call
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_collection():
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def _tokenize(text: str) -> list[str]:
    """Lowercase + strip punctuation tokenizer for BM25."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


@lru_cache(maxsize=10)
def _get_bm25_index(topic: str | None, doc_type: str | None):
    """Build and cache a BM25 index for a given (topic, doc_type) filter pair.

    Called once per unique filter combination — subsequent calls hit the cache.
    Returns (bm25, texts, metas) or (None, [], []) if no matching chunks.
    """
    collection = _get_collection()
    result = collection.get(include=["documents", "metadatas"])
    texts: list[str]  = result["documents"]
    metas: list[dict] = result["metadatas"]

    if topic or doc_type:
        pairs = [
            (t, m) for t, m in zip(texts, metas)
            if (not topic    or m.get("topic")    == topic) and
               (not doc_type or m.get("doc_type") == doc_type)
        ]
        if not pairs:
            return None, [], []
        texts_f, metas_f = zip(*pairs)
        texts, metas = list(texts_f), list(metas_f)

    bm25 = BM25Okapi([_tokenize(t) for t in texts])
    return bm25, texts, metas


# ---------------------------------------------------------------------------
# Internal retrieval helpers
# ---------------------------------------------------------------------------

def _dense_retrieve(
    query: str,
    top_k: int,
    topic: str | None,
    doc_type: str | None,
) -> list[dict[str, Any]]:
    """Dense (ChromaDB embedding) retrieval — returns up to top_k chunks."""
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []

    where: dict[str, Any] | None = None
    filters = {}
    if topic:
        filters["topic"] = topic
    if doc_type:
        filters["doc_type"] = doc_type

    if len(filters) == 1:
        where = filters
    elif len(filters) > 1:
        where = {"$and": [{k: v} for k, v in filters.items()]}

    kwargs: dict[str, Any] = dict(
        query_texts=[query],
        n_results=min(top_k, total),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)
    chunks = []
    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text":     text,
            "source":   meta.get("source",   ""),
            "doc_type": meta.get("doc_type", ""),
            "topic":    meta.get("topic",    ""),
            "page":     meta.get("page",     0),
            "score":    round(dist, 4),
        })
    return chunks


def _bm25_retrieve(
    query: str,
    top_k: int,
    topic: str | None,
    doc_type: str | None,
) -> list[dict[str, Any]]:
    """BM25 keyword retrieval over the chunk corpus (filtered by topic/doc_type)."""
    bm25, texts, metas = _get_bm25_index(topic, doc_type)
    if bm25 is None or not texts:
        return []

    scores = bm25.get_scores(_tokenize(query))
    top_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]

    return [
        {
            "text":     texts[i],
            "source":   metas[i].get("source",   ""),
            "doc_type": metas[i].get("doc_type", ""),
            "topic":    metas[i].get("topic",    ""),
            "page":     metas[i].get("page",     0),
            "score":    round(float(scores[i]), 4),
        }
        for i in top_indices
        if scores[i] > 0   # skip chunks with zero keyword overlap
    ]


def _rrf_merge(
    dense: list[dict[str, Any]],
    bm25:  list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion: score(d) = sum_lists( 1 / (RRF_K + rank) ).

    Chunks appearing near the top of both lists get the highest combined score.
    """
    rrf:       dict[str, float] = {}
    chunk_map: dict[str, dict]  = {}

    for rank, chunk in enumerate(dense):
        key = chunk["text"]
        rrf[key] = rrf.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
        chunk_map[key] = chunk

    for rank, chunk in enumerate(bm25):
        key = chunk["text"]
        rrf[key] = rrf.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
        chunk_map.setdefault(key, chunk)   # keep dense metadata when duplicate

    sorted_keys = sorted(rrf, key=lambda x: -rrf[x])
    result = []
    for key in sorted_keys[:top_k]:
        c = dict(chunk_map[key])
        c["score"] = round(rrf[key], 6)   # RRF score replaces raw L2/BM25 score
        result.append(c)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    topic: str | None = None,
    doc_type: str | None = None,
    use_hybrid: bool = True,
) -> list[dict[str, Any]]:
    """Return the top-k most relevant chunks for *query*.

    Args:
        query:      Natural-language search query.
        top_k:      Number of results to return (default 5).
        topic:      Optional metadata filter. One of:
                    scientific_literature | cultivation_manual | qa_pairs | troubleshooting
        doc_type:   Optional file-type filter: pdf | docx | json | md | txt
        use_hybrid: If True (default), fuse BM25 + dense via RRF.
                    Set False to use dense-only (faster, original behaviour).

    Each returned dict has:
        text     (str)   - the chunk text
        source   (str)   - filename
        doc_type (str)   - pdf | docx | json | md | txt
        topic    (str)   - topic tag
        page     (int)   - page number (1-indexed; 0 for non-PDF)
        score    (float) - RRF score (higher=better) if hybrid,
                           else L2 distance (lower=better) if dense-only
    """
    if _get_collection().count() == 0:
        return []

    # Fetch a wider pool from each retriever before merging
    pool = max(top_k * 2, 10)

    dense_chunks = _dense_retrieve(query, top_k=pool, topic=topic, doc_type=doc_type)

    if not use_hybrid:
        return dense_chunks[:top_k]

    bm25_chunks = _bm25_retrieve(query, top_k=pool, topic=topic, doc_type=doc_type)
    return _rrf_merge(dense_chunks, bm25_chunks, top_k)


def format_context(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved chunks into a single context string for the LLM."""
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks, start=1):
        page_info = f", p.{c['page']}" if c.get("page") else ""
        parts.append(
            f"[Source {i}: {c['source']}{page_info} | {c.get('topic', '')}]\n{c['text']}"
        )
    return "\n\n---\n\n".join(parts)
