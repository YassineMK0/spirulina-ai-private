FROM python:3.10-slim

# System deps needed by PyMuPDF and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/      agent/
COPY api/        api/
COPY rag/        rag/
COPY data/raw/   data/raw/
COPY chat.html   chat.html

# ChromaDB and model cache are mounted as volumes at runtime
# so they persist across container restarts

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
