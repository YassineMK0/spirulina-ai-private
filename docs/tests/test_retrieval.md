# tests/test_retrieval.py

## Purpose
Retrieval quality test — verifies that 10 hand-picked spirulina queries return relevant results from ChromaDB. Requires a populated collection (run ingest first).

## How to run
```bash
.venv\Scripts\python tests/test_retrieval.py
```

## 10 test queries (covering all 4 topics)
| # | Topic | Query |
|---|-------|-------|
| 1 | scientific_literature | Optimal pH for Spirulina platensis |
| 2 | scientific_literature | Light intensity effect on biomass |
| 3 | scientific_literature | Nitrogen and phosphorus requirements |
| 4 | cultivation_manual | How to prepare Zarrouk medium |
| 5 | cultivation_manual | Daily monitoring routine |
| 6 | cultivation_manual | Harvest frequency and filtration |
| 7 | troubleshooting | Why is pH rising sharply? |
| 8 | troubleshooting | Detect and treat contamination |
| 9 | qa_pairs | Normal EC conductivity level |
| 10 | qa_pairs | When to harvest based on OD |

## Pass criterion
`best_chunk_score < 1.5` (L2 distance — lower = more similar)

## Output
For each query: PASS/WARN status, best score, top-5 results with topic, source, page, score, and 120-char preview. A `*` marks chunks that match the expected topic.

## Also runs
`run_filter_checks()` — verifies that topic metadata filters actually restrict results correctly for all 4 topics.

## Dependencies
- `rag.retriever.retrieve` — `retrieve`, `format_context`
