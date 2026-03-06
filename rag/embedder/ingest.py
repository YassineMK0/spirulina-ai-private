"""PDF / DOCX / JSON / Markdown ingestion pipeline -> ChromaDB vector store.

Supported sources and expected folder layout under data/raw/:

    data/raw/
        papers/          ->  .pdf              (topic=scientific_literature)
        manuals/         ->  .pdf, .docx       (topic=cultivation_manual)
        qa/              ->  .json             (topic=qa_pairs)
        troubleshooting/ ->  .md, .txt, .pdf   (topic=troubleshooting)

Run (from project root):
    .venv\\Scripts\\python -m rag.embedder.ingest

Idempotent: existing chunks are replaced via upsert, never duplicated.
Target: 500-1000 clean chunks ready for embedding.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import chromadb
import fitz  # PyMuPDF
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------------------------------------------------------------------
# Config  (all overridable via env vars)
# ---------------------------------------------------------------------------

RAW_DIR        = Path(os.getenv("RAW_DATA_DIR",      "data/raw"))
CHROMA_DIR     = Path(os.getenv("CHROMA_PERSIST_DIR", "data/processed/chroma"))
COLLECTION_NAME = "spirulina_kb"
EMBED_MODEL    = "paraphrase-multilingual-MiniLM-L12-v2"

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50

# Subfolder name  ->  topic tag stored in metadata
TOPIC_MAP: dict[str, str] = {
    "papers":          "scientific_literature",
    "manuals":         "cultivation_manual",
    "qa":              "qa_pairs",
    "troubleshooting": "troubleshooting",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".json", ".md", ".txt"}

# Minimum chunk length (chars) — shorter chunks are discarded as noise
MIN_CHUNK_LEN = 30


# ---------------------------------------------------------------------------
# Text extraction by file type
# ---------------------------------------------------------------------------

def _extract_pdf(path: Path) -> list[tuple[int, str]]:
    """Extract body text page-by-page using PyMuPDF.

    Blocks in the top 8 % and bottom 8 % of each page are discarded to
    strip recurring headers and footers.

    Returns [(page_number_1indexed, text), ...].
    """
    pages: list[tuple[int, str]] = []
    try:
        doc = fitz.open(str(path))
        for page_num, page in enumerate(doc, start=1):
            page_h = page.rect.height
            top_cut    = page_h * 0.08
            bottom_cut = page_h * 0.92

            # blocks: (x0, y0, x1, y1, text, block_no, block_type)
            # Sort blocks top-to-bottom, left-to-right for natural reading order
            blocks = sorted(
                (b for b in page.get_text("blocks")
                 if b[6] == 0              # text block (not image)
                 and b[1] > top_cut        # below header zone
                 and b[3] < bottom_cut),   # above footer zone
                key=lambda b: (round(b[1] / 20) * 20, b[0]),  # row-then-column
            )
            body_parts = [b[4] for b in blocks]
            text = "\n".join(body_parts).strip()
            if text:
                pages.append((page_num, text))
        doc.close()
    except Exception as exc:
        print(f"  [warn] Cannot read {path.name}: {exc}")
    return pages


def _extract_docx(path: Path) -> str:
    """Extract text from all paragraphs in a DOCX file."""
    try:
        doc = DocxDocument(str(path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as exc:
        print(f"  [warn] Cannot read {path.name}: {exc}")
        return ""


def _extract_json_qa(path: Path) -> list[str]:
    """Parse a Q&A JSON file into a list of 'Q: ...\\nA: ...' strings.

    Accepted formats:
        [{"question": "...", "answer": "..."}]         <- list of dicts
        {"pairs": [{"q": "...", "a": "..."}]}          <- dict with key
    Also accepts short keys: "q" / "a" alongside "question" / "answer".
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [warn] Cannot parse {path.name}: {exc}")
        return []

    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("pairs") or data.get("qa") or []

    pairs: list[str] = []
    for item in items:
        q = item.get("question") or item.get("q") or ""
        a = item.get("answer")   or item.get("a") or ""
        if q and a:
            pairs.append(f"Q: {q.strip()}\nA: {a.strip()}")
    return pairs


def _extract_text_file(path: Path) -> str:
    """Read a plain-text or Markdown file."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"  [warn] Cannot read {path.name}: {exc}")
        return ""


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_PAGE_NUM_RE   = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
_EXCESS_WS_RE  = re.compile(r"[ \t]{3,}")
_MULTI_NL_RE   = re.compile(r"\n{3,}")

# Hyphenated line break: "cultiva-\ntion" -> "cultivation"
# Only merge when the hyphen is at end-of-line (not mid-word dash)
_HYPHEN_NL_RE  = re.compile(r"-\n(\s*)")

# Soft hyphen (U+00AD) used in some PDFs
_SOFT_HYPHEN_RE = re.compile(r"\u00ad")

# Citation markers: [1], [2,3], (Smith et al., 2019), [Fig. 2]
_CITATION_RE   = re.compile(r"\[\d[\d,\s\-]*\]|\(\w[\w\s,\.]+\d{4}\w?\)")

# Lone special chars / figure-label lines: "Fig. 1", "Table 2.", "Figure 3:"
_FIGURE_RE     = re.compile(
    r"^\s*(Fig(?:ure)?|Table|Tableau|Tableau|Annexe|Appendix)[\s\.\:]\s*\d+.*$",
    re.MULTILINE | re.IGNORECASE,
)

# PDF ligature characters -> ASCII equivalents
_LIGATURES = {
    "\ufb00": "ff",  # ﬀ
    "\ufb01": "fi",  # ﬁ
    "\ufb02": "fl",  # ﬂ
    "\ufb03": "ffi", # ﬃ
    "\ufb04": "ffl", # ﬄ
    "\ufb05": "st",  # ﬅ
    "\ufb06": "st",  # ﬆ
    "\u2019": "'",   # right single quote -> apostrophe
    "\u2018": "'",
    "\u201c": '"',   # curly double quotes
    "\u201d": '"',
    "\u2013": "-",   # en-dash
    "\u2014": "-",   # em-dash
    "\u00a0": " ",   # non-breaking space
}
_LIGATURE_TABLE = str.maketrans(_LIGATURES)

# Reference section headers (EN + FR) — everything after this is bibliography noise
_REF_SECTION_RE = re.compile(
    r"\n\s*(?:References?|Bibliography|Bibliographie|R[eé]f[eé]rences?|"
    r"Works\s+Cited|Sources?|Literatura)\s*\n",
    re.IGNORECASE,
)


def _fix_ligatures(text: str) -> str:
    """Replace PDF ligature characters and typographic quotes with ASCII."""
    text = _SOFT_HYPHEN_RE.sub("", text)   # remove invisible soft hyphens
    return text.translate(_LIGATURE_TABLE)


def _fix_hyphenation(text: str) -> str:
    """Merge words split across lines by a hyphen: 'cultiva-\\ntion' -> 'cultivation'."""
    return _HYPHEN_NL_RE.sub("", text)


def _strip_references(text: str) -> str:
    """Drop everything from the reference/bibliography section onward."""
    m = _REF_SECTION_RE.search(text)
    if m:
        return text[: m.start()].strip()
    return text


def _is_noisy_chunk(chunk: str) -> bool:
    """Return True for chunks that are mostly noise and should be discarded.

    Noise patterns:
      - Too few words (< 10) — likely a label, caption, or header fragment
      - Too high ratio of non-alphanumeric chars (> 40%) — tables, formulas
      - Purely numeric content — page numbers or table cells that slipped through
    """
    words = chunk.split()
    if len(words) < 8:
        return True
    alpha_chars = sum(c.isalpha() for c in chunk)
    if len(chunk) > 0 and alpha_chars / len(chunk) < 0.40:
        return True
    return False


def _clean(text: str) -> str:
    """Full cleaning pipeline for extracted PDF/text content."""
    # 1. Fix PDF-specific artifacts first
    text = _fix_ligatures(text)
    text = _fix_hyphenation(text)

    # 2. Drop reference section (pure bibliography noise)
    text = _strip_references(text)

    # 3. Remove lone page-number lines
    text = _PAGE_NUM_RE.sub("", text)

    # 4. Remove figure/table label lines
    text = _FIGURE_RE.sub("", text)

    # 5. Strip inline citation markers (reduce noise in chunk text)
    text = _CITATION_RE.sub("", text)

    # 6. Normalize whitespace
    text = _EXCESS_WS_RE.sub(" ", text)   # runs of spaces/tabs -> single space
    text = _MULTI_NL_RE.sub("\n\n", text) # 3+ blank lines -> 2

    return text.strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _make_splitter(
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # Prefer splitting at paragraph > sentence > clause > word boundaries
        separators=["\n\n", ".\n", ". ", "?\n", "? ", "!\n", "! ", "\n", " ", ""],
    )


def _chunk_id(source: str, idx: int, hint: str = "") -> str:
    """Deterministic MD5 ID for a chunk — enables idempotent upserts."""
    return hashlib.md5(f"{source}::{idx}::{hint}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def _topic(path: Path, raw_dir: Path) -> str:
    """Infer topic from the immediate subfolder under raw_dir."""
    try:
        parts = path.relative_to(raw_dir).parts
        subfolder = parts[0] if len(parts) > 1 else "general"
        return TOPIC_MAP.get(subfolder, subfolder)
    except ValueError:
        return "general"


def _doc_type(path: Path) -> str:
    return path.suffix.lstrip(".").lower() or "txt"


# ---------------------------------------------------------------------------
# Per-file processor  ->  (ids, documents, metadatas)
# ---------------------------------------------------------------------------

def _process_file(
    path: Path,
    raw_dir: Path,
    splitter: RecursiveCharacterTextSplitter,
) -> tuple[list[str], list[str], list[dict]]:
    dt    = _doc_type(path)
    topic = _topic(path, raw_dir)
    source = path.name
    base  = {"source": source, "doc_type": dt, "topic": topic}

    ids: list[str]    = []
    docs: list[str]   = []
    metas: list[dict] = []

    def _add(chunk: str, page: int, chunk_idx: int) -> None:
        chunk = chunk.strip()
        if len(chunk) < MIN_CHUNK_LEN:
            return
        if _is_noisy_chunk(chunk):   # filter table cells, captions, short fragments
            return
        cid = _chunk_id(source, len(ids), f"p{page}c{chunk_idx}")
        ids.append(cid)
        docs.append(chunk)
        metas.append({**base, "page": page, "chunk": chunk_idx})

    if dt == "pdf":
        for page_num, raw_text in _extract_pdf(path):
            for i, chunk in enumerate(splitter.split_text(_clean(raw_text))):
                _add(chunk, page_num, i)

    elif dt == "docx":
        for i, chunk in enumerate(splitter.split_text(_clean(_extract_docx(path)))):
            _add(chunk, 0, i)

    elif dt == "json":
        for qa_idx, pair in enumerate(_extract_json_qa(path)):
            for j, chunk in enumerate(splitter.split_text(pair)):
                _add(chunk, 0, qa_idx * 100 + j)

    elif dt in ("md", "txt"):
        for i, chunk in enumerate(splitter.split_text(_clean(_extract_text_file(path)))):
            _add(chunk, 0, i)

    else:
        print(f"  [skip] {path.name} — unsupported type '{dt}'")

    return ids, docs, metas


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest(
    raw_dir: Path = RAW_DIR,
    chroma_dir: Path = CHROMA_DIR,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    collection_name: str = COLLECTION_NAME,
    verbose: bool = True,
) -> int:
    """Ingest all supported files under raw_dir into ChromaDB.

    Args:
        raw_dir:         Root folder containing KB source files.
        chroma_dir:      ChromaDB persistence directory.
        chunk_size:      Characters per chunk (tune: 300 / 500 / 800).
        chunk_overlap:   Overlap between consecutive chunks.
        collection_name: ChromaDB collection name (use different names for
                         tuning experiments, e.g. 'spirulina_kb_300').
        verbose:         Print progress lines (set False during grid search).

    Returns:
        Total number of chunks in the collection after ingestion.
    """
    all_files = sorted(
        p for p in raw_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not all_files:
        if verbose:
            print(f"No supported files found under {raw_dir}")
            print(f"  Place .pdf / .docx / .json / .md files in subfolders:")
            print(f"  {raw_dir}/papers/  manuals/  qa/  troubleshooting/")
        return 0

    splitter = _make_splitter(chunk_size, chunk_overlap)

    if verbose:
        print(f"Files found     : {len(all_files)}")
        print(f"Embedding model : {EMBED_MODEL}")
        print(f"Chunk size      : {chunk_size}  overlap={chunk_overlap}")
        print(f"Collection      : {collection_name}")
        print(f"ChromaDB path   : {chroma_dir}")
        print()

    chroma_dir.mkdir(parents=True, exist_ok=True)
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
    )

    run_total = 0

    for file_path in all_files:
        dt    = _doc_type(file_path)
        topic = _topic(file_path, raw_dir)
        if verbose:
            print(f"  -> {file_path.name:<40} [{dt} | {topic}]")

        ids, docs, metas = _process_file(file_path, raw_dir, splitter)
        if not ids:
            if verbose:
                print(f"     0 chunks (empty or unreadable)")
            continue

        BATCH = 100
        for i in range(0, len(ids), BATCH):
            collection.upsert(
                ids=ids[i : i + BATCH],
                documents=docs[i : i + BATCH],
                metadatas=metas[i : i + BATCH],
            )

        if verbose:
            print(f"     {len(ids)} chunks")
        run_total += len(ids)

    final = collection.count()
    if verbose:
        print()
        print(f"Done.")
        print(f"  This run ingested : {run_total} chunks")
        print(f"  Collection total  : {final} chunks")
        if final < 500:
            print(f"  [note] {final} chunks < 500 target. Add more KB files.")
        elif final > 1000:
            print(f"  [note] {final} chunks > 1000 target. Consider larger chunk_size.")
        else:
            print(f"  [ok]   Chunk count in target range (500-1000).")

    return final


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ingest()
