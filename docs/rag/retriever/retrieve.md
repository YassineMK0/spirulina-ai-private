# rag/retriever/retrieve.py

## Purpose
Retrieves the most relevant knowledge chunks for a user query using a hybrid BM25 + dense (ChromaDB) retrieval system fused with Reciprocal Rank Fusion (RRF).

## Embedding model
**Default:** `BAAI/bge-m3` (configurable via `EMBED_MODEL` env var — must match `ingest.py`)

## Public API

### `retrieve(query, top_k=5, topic=None, doc_type=None, use_hybrid=True) -> list[dict]`
Returns top-k most relevant chunks. Each chunk dict has:
- `text` — the chunk content
- `source` — filename
- `doc_type` — pdf | docx | json | md | txt
- `topic` — topic tag
- `page` — page number (0 for non-PDF)
- `score` — RRF score (higher = better) if hybrid, L2 distance if dense-only

### `format_context(chunks) -> str`
Formats chunks into a single context string for the LLM:
```
[Source 1: filename.pdf, p.12 | topic]
chunk text...

---

[Source 2: ...]
```

## How hybrid retrieval works
1. **Dense**: ChromaDB embedding search → top `pool` results (ranked by L2 distance)
2. **BM25**: Keyword index over all corpus chunks → top `pool` results (by BM25 score)
3. **RRF merge**: `score(chunk) = 1/(RRF_K + dense_rank) + 1/(RRF_K + bm25_rank)`
   - `pool = max(top_k * 2, 10)` — wider pool from each retriever before merging
   - `RRF_K = 60` — smoothing constant
   - Chunks ranking well in BOTH lists bubble to the top

## Caching
- `_get_collection()`: `@lru_cache(maxsize=1)` — ChromaDB connection loaded once
- `_get_bm25_index(topic, doc_type)`: `@lru_cache(maxsize=10)` — BM25 index built once per unique filter combination, then reused
- Pre-warmed at API startup via `api/main.py` lifespan

## Filtering
Optional `topic` and `doc_type` filters narrow both dense and BM25 retrieval.
Valid topics: `scientific_literature | cultivation_manual | qa_pairs | troubleshooting`

## Configuration
| Variable | Default | Env override |
|----------|---------|-------------|
| `CHROMA_DIR` | `data/processed/chroma` | `CHROMA_PERSIST_DIR` |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | — |
| `DEFAULT_TOP_K` | 5 | — |
| `RRF_K` | 60 | — |

## Current settings in production
`top_k=8` used in the pipeline (set in `nodes.py`).

## Dependencies
- `chromadb` — vector store
- `sentence-transformers` — embedding model
- `rank_bm25` — BM25 keyword index
