# notebooks/ — Exploratory Data Analysis

Jupyter notebooks for data exploration, model prototyping, and
visualisation. Nothing here is imported by the main pipeline.

**Status: empty — planned for use during ML model development.**

---

## Planned Notebooks

### `01_data_exploration.ipynb`
Explore raw sensor data: pH, EC, temperature, OD distributions.
Plot time series, identify outliers, check for missing values.

### `02_growth_model_prototype.ipynb`
Prototype the growth prediction model.
Feature engineering → train/test split → XGBoost → evaluation metrics.

### `03_anomaly_detection.ipynb`
Prototype the Isolation Forest anomaly detector.
Tune contamination parameter, visualise decision boundary.

### `04_harvest_readiness.ipynb`
Analyse OD vs harvest yield correlation.
Build the harvest-readiness threshold rule.

### `05_rag_quality.ipynb`
Interactive retrieval quality analysis.
Run queries, inspect retrieved chunks, visualise embedding space (UMAP).

---

## Running Notebooks

```bash
.venv/Scripts/jupyter lab
```

or

```bash
.venv/Scripts/jupyter notebook
```
