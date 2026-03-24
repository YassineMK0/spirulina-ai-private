# agent/sensors.py

## Purpose
Provides the sensor reading interface. Currently mock-based; designed to be swapped for a real IoT API call with zero changes to the rest of the pipeline.

## Public functions

### `get_sensor_reading(container_id: str) -> dict`
Returns a dict of sensor readings. Empty dict if no container_id.

**Priority order:**
1. Named fake containers (static values — for testing)
2. Fallback: deterministic random values seeded by `container_id`

**Returned schema:**
| Key | Type | Unit | Healthy range |
|-----|------|------|--------------|
| `ph` | float | — | 8.5 – 10.5 |
| `temperature_c` | float | C | 30 – 37 |
| `od680` | float | g/L | 0.3 – 1.5 |
| `conductivity_ms` | float | mS/cm | 18 – 28 |
| `dissolved_o2_pct` | float | % | 80 – 110 |
| `light_lux` | float | lux | 5000 – 15000 |
| `co2_ppm` | float | ppm | 350 – 700 |
| `timestamp` | str | ISO-8601 UTC | — |
| `status` | str | — | "ok" / "warning" / "error" |

### Named Fake Containers (testing)
Use these as `container_id` in the chat UI to trigger reasoning scenarios:

| Container ID | Scenario | Key anomaly |
|---|---|---|
| `test-healthy` | All values optimal | None |
| `test-harvest-ready` | Ready to harvest | OD680 = 1.15 |
| `test-ph-crash` | pH too low | pH = 7.2, warning |
| `test-heat-stress` | Overheating | temp = 41.5 C, low O2 |
| `test-high-ec` | Salt build-up | EC = 38 mS/cm |
| `test-multi-anomaly` | Multiple issues | pH 7.8 + temp 40 C + O2 55% |

### `format_sensor_summary(reading: dict) -> str`
Formats the sensor dict into a compact human-readable string injected into the LLM prompt.

## How to connect real IoT data
Replace the body of `get_sensor_reading()` with:
```python
resp = requests.get(f"{SENSOR_API_URL}/containers/{container_id}/latest",
                    headers={"Authorization": f"Bearer {API_TOKEN}"})
return resp.json()
```
Keep the return schema identical — no other files need to change.

## Dependencies
- `random` (fallback mock randomization)
- `datetime` (timestamp generation)
