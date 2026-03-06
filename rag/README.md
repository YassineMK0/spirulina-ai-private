# RAG Pipeline — Spirulina AI Assistant

Retrieval-Augmented Generation pipeline that turns raw KB documents into
searchable vector chunks and injects the most relevant passages into the
LLM context at query time.

---

## Folder Structure

```
rag/
├── embedder/
│   └── ingest.py        # Document ingestion pipeline (PDF/DOCX/JSON/MD)
├── retriever/
│   └── retrieve.py      # ChromaDB query wrapper with metadata filters
├── generator/           # (reserved) LLM response generation node
└── README.md            # This file
```

---

## Data Layout

Place all KB source files under `data/raw/` before running ingestion.
The subfolder name controls the `topic` tag attached to every chunk.

```
data/raw/
    papers/              # Scientific PDFs  -> topic=scientific_literature
    manuals/             # PDF or DOCX manuals, SpirulinaAI_Documentation.docx
                         #                  -> topic=cultivation_manual
    qa/                  # JSON Q&A pairs   -> topic=qa_pairs
    troubleshooting/     # .md or .txt      -> topic=troubleshooting
```

ChromaDB index is written to:
```
data/processed/chroma/   # persistent vector store (auto-created)
```

---

## Supported File Types

| Extension | Extractor | Notes |
|-----------|-----------|-------|
| `.pdf` | PyMuPDF (`fitz`) | Header/footer stripped (top+bottom 8% of page) |
| `.docx` | `python-docx` | All paragraphs extracted |
| `.json` | Custom parser | Supports `question/answer` and `q/a` key formats |
| `.md` / `.txt` | Plain read | Whitespace-normalized |

---

## Chunk Metadata

Every chunk stored in ChromaDB carries:

| Field | Type | Example |
|-------|------|---------|
| `source` | str | `"zarrouk_manual.pdf"` |
| `doc_type` | str | `"pdf"` |
| `topic` | str | `"cultivation_manual"` |
| `page` | int | `3` (0 for non-PDF) |
| `chunk` | int | `1` |

---

## Running Ingestion

From the project root:

```bash
.venv/Scripts/python -m rag.embedder.ingest
```

The script is **idempotent** — re-running replaces existing chunks via upsert,
never duplicates them. Target is **500–1000 chunks** across the full KB.

### Ingestion with custom chunk size (for tuning)

```python
from rag.embedder.ingest import ingest

ingest(chunk_size=300, chunk_overlap=30, collection_name="spirulina_kb_300")
ingest(chunk_size=500, chunk_overlap=50, collection_name="spirulina_kb_500")
ingest(chunk_size=800, chunk_overlap=80, collection_name="spirulina_kb_800")
```

---

## Retrieval

```python
from rag.retriever.retrieve import retrieve, format_context

# Top-5 results, no filter
chunks = retrieve("What is the optimal pH for spirulina?", top_k=5)

# Filter by topic
chunks = retrieve("pH rising sharply", top_k=5, topic="troubleshooting")
chunks = retrieve("biomass productivity", top_k=5, topic="scientific_literature")

# Filter by file type
chunks = retrieve("Zarrouk medium recipe", top_k=5, doc_type="pdf")

# Format for LLM prompt
context = format_context(chunks)
```

Each returned chunk dict:

```python
{
    "text":     "...",              # chunk content
    "source":   "paper1.pdf",      # filename
    "doc_type": "pdf",
    "topic":    "scientific_literature",
    "page":     4,                  # 0 for non-PDF sources
    "score":    0.312,              # L2 distance — lower = more similar
}
```

Valid `topic` filter values:
- `scientific_literature`
- `cultivation_manual`
- `qa_pairs`
- `troubleshooting`

---

## Embedding Model

**`paraphrase-multilingual-MiniLM-L12-v2`** (sentence-transformers)

- Free, runs fully local — no API key required
- Handles English + French documents
- 384-dimensional embeddings
- Downloads automatically on first run (~420 MB, cached in `~/.cache/`)

---

## Tuning

Run the grid search to find the best chunk_size / top_k combination:

```bash
.venv/Scripts/python tests/tune_retrieval.py
```

This evaluates 18 configurations (3 chunk sizes × 3 top-k values × filtered/unfiltered)
against the 20-query eval set in `tests/eval_set.py`.
Target: **>80% hit rate** at top-5.

---

## Dependencies

```
pymupdf>=1.24.0
python-docx>=1.1.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
langchain-text-splitters>=0.3.0
```

Install:
```bash
.venv/Scripts/pip install -r requirements.txt
```
