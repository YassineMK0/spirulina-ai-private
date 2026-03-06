# rag/retriever/ — Vector Store Retriever

Wraps ChromaDB query into a simple Python function used by the
`retrieve_rag` graph node.

---

## File

### `retrieve.py`

Loads the ChromaDB collection once (lazy `lru_cache` singleton) and
exposes two public functions.

---

### `retrieve(query, top_k, topic, doc_type)`

Returns the top-k most similar chunks for a query.

```python
from rag.retriever.retrieve import retrieve

# Basic — no filter
chunks = retrieve("What is the optimal pH for spirulina?", top_k=5)

# Filter by topic
chunks = retrieve("pH instability", top_k=5, topic="troubleshooting")

# Filter by file type
chunks = retrieve("Zarrouk recipe", top_k=5, doc_type="pdf")

# Both filters combined
chunks = retrieve("daily monitoring", top_k=5,
                  topic="cultivation_manual", doc_type="docx")
```

Valid `topic` values:
`scientific_literature` | `cultivation_manual` | `qa_pairs` | `troubleshooting`

Each returned chunk dict:
```python
{
    "text":     "...",              # chunk content
    "source":   "paper1.pdf",
    "doc_type": "pdf",
    "topic":    "scientific_literature",
    "page":     4,                  # 0 for non-PDF sources
    "score":    0.312,              # L2 distance — lower = more similar
}
```

---

### `format_context(chunks)`

Formats a list of chunks into a single string ready to inject into the
LLM system prompt.

```python
from rag.retriever.retrieve import retrieve, format_context

chunks  = retrieve("optimal pH", top_k=5)
context = format_context(chunks)
# "[Source 1: paper1.pdf, p.4 | scientific_literature]\n..."
```

---

## Config

| Env var | Default | Description |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `data/processed/chroma` | ChromaDB storage path |

Embedding model: `paraphrase-multilingual-MiniLM-L12-v2`
(must match what was used during ingestion).
