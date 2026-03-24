# rag/embedder/ingest.py

## Purpose
Ingestion pipeline: reads source documents from `data/raw/`, cleans and chunks them, embeds them, and upserts into ChromaDB. Idempotent — existing chunks are replaced via upsert, never duplicated.

## How to run
```bash
.venv\Scripts\python -m rag.embedder.ingest
```

## Embedding model
**Default:** `BAAI/bge-m3` (configurable via `EMBED_MODEL` env var)

`bge-m3` is multilingual (100+ languages), large (1024 dims), and handles the French+English corpus better than the previous MiniLM model.

> **Important:** if you change `EMBED_MODEL`, you must re-run ingest — the old vectors in ChromaDB were built with a different model and are incompatible.

## Supported file types and folder mapping

| Folder | File types | `topic` tag |
|--------|-----------|------------|
| `data/raw/papers/` | `.pdf` | `scientific_literature` |
| `data/raw/manuals/` | `.pdf`, `.docx` | `cultivation_manual` |
| `data/raw/qa/` | `.json` | `qa_pairs` |
| `data/raw/troubleshooting/` | `.md`, `.txt`, `.pdf` | `troubleshooting` |
| `data/raw/` (root) | any | `general` |

## Configuration
| Variable | Default | Env override |
|----------|---------|-------------|
| `RAW_DIR` | `data/raw` | `RAW_DATA_DIR` |
| `CHROMA_DIR` | `data/processed/chroma` | `CHROMA_PERSIST_DIR` |
| `CHUNK_SIZE` | 500 chars | — |
| `CHUNK_OVERLAP` | 50 chars | — |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | — |

## Text extraction pipeline (per file type)
- **PDF** (`_extract_pdf`): Uses PyMuPDF. Strips top/bottom 8% of each page (headers/footers). Sorts blocks top-to-bottom, left-to-right.
- **DOCX** (`_extract_docx`): Extracts all paragraphs.
- **JSON** (`_extract_json_qa`): Parses Q&A pairs into `"Q: ...\nA: ..."` strings.
- **MD/TXT** (`_extract_text_file`): Reads raw text.

## Cleaning pipeline (`_clean`)
1. Fix PDF ligatures (ﬁ→fi, ﬂ→fl, curly quotes, en-dashes)
2. Fix hyphenated line breaks (`cultiva-\ntion` → `cultivation`)
3. Strip reference/bibliography sections
4. Remove lone page-number lines
5. Remove figure/table label lines
6. Normalize whitespace

## Noise filtering (`_is_noisy_chunk`)
Chunks are discarded if:
- Fewer than 8 words
- Less than 40% alphabetic characters (tables, formulas)

## Chunking
Uses `RecursiveCharacterTextSplitter` with separator priority: `\n\n` > `.\n` > `. ` > `\n` > ` `

## Chunk IDs
Deterministic MD5 hash of `source::index::hint` — enables idempotent upserts on re-ingestion.

## Batch upsert
Chunks are upserted in batches of 100 to avoid memory issues on large corpora.

## Current corpus
5,356 chunks from 20+ files (French + English PDFs).

## Dependencies
- `chromadb` — vector store
- `sentence-transformers` — embedding model
- `pymupdf` (fitz) — PDF extraction
- `python-docx` — DOCX extraction
- `langchain-text-splitters` — chunking
