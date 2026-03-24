# requirements.txt

## Purpose
Python dependencies for the SpirulinaAI project.

## Key packages

### LLM / Agent
- `langchain`, `langchain-core`, `langchain-groq`, `langchain-openai` — LLM chains and providers
- `langgraph` — stateful agent pipeline
- `groq` — Groq API client (RAG generator: Llama 3.3 70b, router: Llama 3.1 8b)

### RAG / Embeddings
- `chromadb` — vector store
- `sentence-transformers` — BAAI/bge-m3 embedding model (1024 dims, multilingual)
- `rank-bm25` — BM25 sparse retrieval for hybrid RRF search

### API / Server
- `fastapi`, `uvicorn` — HTTP server for chat.html backend
- `python-dotenv` — environment variable loading

### Memory
- `redis` — conversation memory (falls back to in-memory if unavailable)

## Install
```bash
pip install -r requirements.txt
```
