# Phase B — ML Model Interface Specification

**Goal:** plug trained ML models into the existing `run_ml_models` node so the
formatter's harvest window, forecast table, and anomaly banner all activate.

No changes to the graph, the formatter, or the LLM prompts are needed —
`ml_outputs` is the single integration boundary.

---

## Integration point in the pipeline

```
read_sensors  ->  run_ml_models  ->  [reasoning_agent | generate_response]
                       |
                  ml_outputs: dict
```

`run_ml_models` in `agent/nodes.py` currently returns `state["ml_outputs"]`
unchanged. Phase B replaces that body with calls to each model and populates
the dict. Every downstream consumer (formatter, LLM prompts) already reads
from this dict.

---

## Model 1 — Growth / OD680 Forecast

**Purpose:** predict OD680 in 60 minutes given current readings.  
**Used by:** `template_prediction()`, reasoning LLM prompt, `run_ml_models`.

### Input

```python
sensor: dict  # from read_sensors — same schema as agent/sensors.py
# Required keys:
#   od680            float   current OD at 680 nm
#   temperature_c    float   °C
#   light_lux        float   lux
#   ph               float
#   conductivity_ms  float   mS/cm
# Optional:
#   dissolved_o2_pct float
#   co2_ppm          float
```

### Output contract — `ml_outputs["growth_prediction"]`

```python
{
    "OD680": {
        "current":  float,   # echoes sensor["od680"]
        "in_60min": float,   # predicted value 60 min from now
        "trend":    str,     # "Rising", "Stable", or "Declining"
    },
    # Add more metrics as available:
    # "pH":   { "current": ..., "in_60min": ..., "trend": ... },
}
```

**Formatter behaviour:** `template_prediction()` renders a two-column table
(Now vs In 60 min) for every key in this dict. Extra keys appear automatically.

### Suggested model type

Gradient-boosted regressor (LightGBM / XGBoost) trained on rolling time-series
windows. Input: last N readings (N=6, 10-min intervals). Output: scalar OD680.

---

## Model 2 — Harvest Readiness

**Purpose:** decide whether to harvest now, soon, or wait; estimate yield.  
**Used by:** `template_harvest_card()`, reasoning LLM, HARVEST intent path.

### Input

```python
sensor: dict   # same as above
# Key driver: od680 (biomass proxy)
# Secondary: temperature_c, conductivity_ms (affect dry-weight yield)
```

### Output contract — `ml_outputs["harvest_readiness"]`

Option A — simple (scalar):
```python
"harvest_readiness": "harvest in 2 days"   # plain string -> shown as-is
```

Option B — structured (preferred):
```python
"harvest_readiness": {
    "current_od": float,       # OD680 now
    "early": {
        "timing": str,         # e.g. "Now (suboptimal)"
        "yield":  str,         # e.g. "~160 g/m²"
    },
    "balanced": {
        "timing": str,         # e.g. "Tomorrow"
        "yield":  str,         # e.g. "~400 g/m²"
    },
    "optimal": {
        "timing": str,         # e.g. "+2 days"
        "yield":  str,         # e.g. "~510 g/m²"
    },
}
```

**Formatter behaviour:** structured output renders a three-row scenario table.
Scalar output renders a single-row recommendation.

### Suggested model type

Rule-based baseline (OD680 threshold + growth rate trend) is sufficient for v1.
Upgrade to a classifier (Random Forest / logistic regression) trained on labelled
harvest events when historical data is available.

---

## Model 3 — Anomaly Detection

**Purpose:** flag unusual sensor patterns that rule-based thresholds miss.  
**Used by:** `format_message()` alert path, reasoning LLM for SYSTEM intent.

### Input

```python
sensor: dict   # full reading, all keys
# The model scores the entire reading as a vector
```

### Output contract — `ml_outputs["anomaly_flag"]` + `ml_outputs["anomaly_detail"]`

```python
"anomaly_flag":   bool,   # True if anomaly detected
"anomaly_detail": str,    # human-readable description, e.g.:
                          # "OD680 dropped 0.3 units in 30 min — unusually fast"
                          # "pH and O2 diverging from expected co-trend"
```

**Formatter behaviour:** when `anomaly_flag=True`, an amber ⚠️ banner is
injected regardless of intent. The detail string goes into the banner message.

### Suggested model type

Isolation Forest or Autoencoder trained on normal-condition readings.
Threshold on anomaly score to set sensitivity. Consider a sliding-window input
(last 3–6 readings) to catch rate-of-change anomalies (e.g. fast pH drop).

---

## Putting it together — `run_ml_models` node (Phase B body)

```python
def run_ml_models(state: AgentState) -> dict[str, Any]:
    sensor = state.get("last_sensor_state") or {}
    if not sensor:
        return {"ml_outputs": {}}

    from ml.growth    import predict_growth       # Model 1
    from ml.harvest   import predict_harvest      # Model 2
    from ml.anomaly   import detect_anomaly       # Model 3

    growth   = predict_growth(sensor)
    harvest  = predict_harvest(sensor)
    flag, detail = detect_anomaly(sensor)

    return {
        "ml_outputs": {
            "growth_prediction": growth,
            "harvest_readiness": harvest,
            "anomaly_flag":      flag,
            "anomaly_detail":    detail,
        }
    }
```

Each model function receives the sensor dict and returns its contract output.
No changes elsewhere in the graph.

---

## Data Collection Strategy

### Option A — Physics-based Simulator (recommended for Phase B start)

Build a differential-equation simulator of spirulina batch culture:

```
dX/dt  = mu(I, T, pH, N) * X - D * X         # biomass (OD680 proxy)
dpH/dt = f(photosynthesis, CO2, buffer)
dEC/dt = g(evaporation, nutrient uptake, D)
dO2/dt = h(photosynthesis, respiration, aeration)
```

Where:
- `mu` = Monod-type growth rate (light + temperature + pH + nutrient limited)
- `D` = dilution rate (0 for batch, >0 for semi-continuous)
- Parameters from published *S. platensis* kinetic models (Cornet 1992, Sukenik 2009)

**Advantages:** free, instant, controllable anomaly injection, no privacy issues.  
**Disadvantages:** model error in tails (extreme pH, contamination events).

**Suggested noise:** add Gaussian noise to each parameter (σ ≈ 2–5 % of range),
plus occasional step-change anomalies (pH drop event, sensor drift, pump failure).

### Option B — Real Container Logging

Instrument the physical container with:
- pH probe (Atlas Scientific EZO-pH)
- EC probe (Atlas Scientific EZO-EC)
- Temperature (DS18B20)
- OD680 (custom turbidity cell or benchtop spectrophotometer at sampling times)

Log every 5–10 minutes to a SQLite or InfluxDB local file.
Label harvest events and anomaly events manually in a `labels.csv`.

**Minimum for useful ML:** 30 full batch cycles (~30 × 5 days = 150 days).

### Recommended approach

Start with the simulator to build and validate model architectures (2–3 weeks).
Collect real data in parallel from one container as ground-truth.
Fine-tune or retrain on real data once 30+ cycles are available.

---

## Directory layout for Phase B

```
ml/
  data/
    simulator.py          # physics-based data generator
    generate_dataset.py   # CLI: python -m ml.data.generate_dataset --n-cycles 200
    spirulina_sim.csv     # generated training data (not committed if large)
    labels.csv            # manual anomaly / harvest labels (real data)
  growth/
    train.py              # training script -> saves model.pkl
    model.pkl             # trained model artifact
    __init__.py           # predict_growth(sensor) -> growth_prediction dict
  harvest/
    train.py
    model.pkl
    __init__.py           # predict_harvest(sensor) -> harvest_readiness dict
  anomaly/
    train.py
    model.pkl
    __init__.py           # detect_anomaly(sensor) -> (bool, str)
notebooks/
  01_eda_simulator.ipynb          # explore simulated data
  02_growth_prediction.ipynb      # train + evaluate growth model
  03_harvest_readiness.ipynb      # train + evaluate harvest model
  04_anomaly_detection.ipynb      # train + evaluate anomaly model
  05_end_to_end_integration.ipynb # wire ml_outputs into agent state manually
```
