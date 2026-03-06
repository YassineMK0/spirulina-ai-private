# rag/embedder/ — Document Ingestion Pipeline

Reads every KB source file, cleans and chunks the text, and upserts
the chunks into ChromaDB with metadata.

---

## File

### `ingest.py`

**Extraction** — one extractor per file type:

| Format | Extractor | Special handling |
|---|---|---|
| `.pdf` | PyMuPDF (`fitz`) | Strips top/bottom 8% of each page (headers/footers) |
| `.docx` | `python-docx` | Paragraph-by-paragraph |
| `.json` | Custom parser | Each `{question, answer}` pair becomes one unit |
| `.md` / `.txt` | Plain read | Whitespace normalization |

**Cleaning** — applied to all text before chunking:
- Removes lone page-number lines (`^\d+$`)
- Collapses runs of spaces/tabs
- Normalizes multiple blank lines to a maximum of two

**Chunking** — `RecursiveCharacterTextSplitter`:
- Default: `chunk_size=500`, `chunk_overlap=50`
- Separators tried in order: `\n\n` → `\n` → `. ` → ` ` → `""`
- Chunks shorter than 30 characters are discarded as noise

**Metadata** stored per chunk:

```python
{
    "source":   "filename.pdf",
    "doc_type": "pdf",                      # pdf | docx | json | md | txt
    "topic":    "scientific_literature",    # from subfolder name
    "page":     4,                          # 0 for non-PDF
    "chunk":    1,
}
```

**Topic mapping** (subfolder → tag):
```
data/raw/papers/          -> scientific_literature
data/raw/manuals/         -> cultivation_manual
data/raw/qa/              -> qa_pairs
data/raw/troubleshooting/ -> troubleshooting
```

**Storage** — ChromaDB upsert in batches of 100. Idempotent (same chunk
ID = replace, not duplicate). IDs are MD5 hashes of `source::idx::hint`.

---

## Usage

Standard ingestion (default chunk_size=500):
```bash
.venv/Scripts/python -m rag.embedder.ingest
```

Custom chunk size (for tuning experiments):
```python
from rag.embedder.ingest import ingest

ingest(chunk_size=300, chunk_overlap=30, collection_name="spirulina_kb_300")
```

Target: **500–1000 chunks** for the full KB.
