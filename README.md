# Spirulina — LangGraph Agent Pipeline

## Folder structure

```
├── agent/          LangGraph graph definition, state schema, and node functions.
│                   Each node is one pipeline stage (intent, RAG, ML, response).
│
├── rag/            Retrieval-Augmented Generation components.
│   ├── embedder/   Text → vector embedding logic.
│   ├── retriever/  Vector-store query / similarity search.
│   └── generator/  Prompt construction + LLM call for RAG answers.
│
├── ml/             Machine-learning models (one subfolder per model).
│                   Placeholder — models will be added here later.
│
├── api/            FastAPI application exposing the agent as an HTTP service.
│
├── data/
│   ├── raw/        Unprocessed source data (sensor dumps, CSVs, etc.).
│   └── processed/  Cleaned / transformed data, vector-store files.
│
├── notebooks/      Jupyter notebooks for EDA and experimentation.
│
├── requirements.txt
├── .env.template   Copy to .env and fill in secrets before running.
└── README.md       ← you are here
```

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.template .env                           # then edit .env
python -m agent.graph                             # smoke-test the graph
```
