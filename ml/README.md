# ml/ — Machine Learning Models

Holds one subfolder per ML model. Each model is trained offline and
loaded at inference time by the `run_ml_models` node in the LangGraph
pipeline.

**Status: planned — not yet implemented.**

---

## Planned Models

### Growth Prediction
Predicts biomass concentration (g/L) over the next 24–72 hours based on
current sensor readings and recent trends.

- Input: pH, EC, temperature, light intensity, OD, time of day
- Output: predicted biomass at T+24h, T+48h, T+72h
- Algorithm: gradient boosting (XGBoost or LightGBM)

### Anomaly Detection
Flags abnormal sensor readings that may indicate contamination, equipment
failure, or culture stress.

- Input: rolling window of pH, EC, temperature, OD readings
- Output: anomaly score + affected parameter
- Algorithm: Isolation Forest

### Harvest Readiness
Decides whether the culture is ready to harvest based on biomass density
and growth rate trajectory.

- Input: OD history, growth rate estimate, last harvest date
- Output: harvest recommendation (ready / not ready / harvest in N days)
- Algorithm: rule-based threshold + regression

---

## Planned Folder Structure

```
ml/
    growth_prediction/
        train.py           # training script
        model.joblib       # serialized trained model
        predict.py         # inference function used by run_ml_models node
    anomaly_detection/
        train.py
        model.joblib
        predict.py
    harvest_readiness/
        train.py
        model.joblib
        predict.py
```

---

## Integration Point

The `run_ml_models` node in `agent/nodes.py` will import each model's
`predict.py` and merge outputs into `state["ml_outputs"]`:

```python
state["ml_outputs"] = {
    "growth_prediction": {"t24h": 1.8, "t48h": 2.1},
    "anomaly":           {"score": 0.12, "flag": False},
    "harvest_ready":     {"decision": "harvest in 2 days"},
}
```

The RAG generator then incorporates these predictions into its answer
when `has_container=True`.
