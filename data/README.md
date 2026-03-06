# data/ — Knowledge Base & Vector Store

All source documents and generated indices live here.
Never commit `processed/` to git — it can always be regenerated from `raw/`.

---

## raw/ — Source Documents

KB source files read by the ingestion pipeline.

**Current files (all PDFs, placed in root):**

| File | Type | Content |
|---|---|---|
| `Alain-Casal-livre-blanc-spiruline.pdf` | Scientific | White paper on Spirulina |
| `CultivezVotreSpiruline.pdf` | Manual | Cultivation guide |
| `La Spiruline _ propriétés nutritionnelles, applications.pdf` | Scientific | Nutritional properties |
| `Spirulina platensis et ses constituants_intérêts.pdf` | Scientific | Constituents & interest |
| `SpirulinaAI_Documentation.pdf` | Project doc | This project's documentation |
| `The adaptation of growing spirulina (Arthrospira Platensis)...pdf` | Scientific | Growth adaptation study |
| `culture artisanal.pdf` | Manual | Artisanal culture guide |
| `culture-et-production-de-spirulina-platensis-dans-les-eaux.pdf` | Scientific | Production in water bodies |
| `spiruline_Manuel.resume-.J-P.Jourdan.-.Antenna.ch.48p.pdf` | Manual | Jourdan cultivation manual |

**Recommended subfolder organization** (for automatic topic tagging):

```
data/raw/
    papers/          ->  topic = scientific_literature
    manuals/         ->  topic = cultivation_manual
    qa/              ->  topic = qa_pairs          (.json files)
    troubleshooting/ ->  topic = troubleshooting   (.md files)
```

Files placed directly in `data/raw/` (not in a subfolder) get
`topic = general`.

---

## processed/ — Generated Indices

```
processed/
    chroma/          # ChromaDB persistent vector store
                     # Auto-created by the ingestion pipeline
                     # Do NOT edit manually
```

To regenerate from scratch:
```bash
# Delete the store
rm -rf data/processed/chroma

# Re-ingest
.venv/Scripts/python -m rag.embedder.ingest
```

---

## .gitignore recommendation

```gitignore
data/processed/
data/raw/*.pdf
data/raw/*.docx
```

Keep source documents out of git (large binaries). Store them in shared
cloud storage (Google Drive, OneDrive) and download before running ingest.
