# agent/formatter.py

## Purpose
Converts the raw LLM answer and state data into rich markdown output. It selects and combines visual templates based on what data is available and what the user's intent was.

## Public entry point
```python
format_message(raw_answer, intent, has_container, rag_context, sensor, ml_outputs, container_id) -> str
```
Always includes the LLM answer. Adds extra cards when relevant data is present.

## Five templates

| # | Name | When shown | Content |
|---|------|-----------|---------|
| 1 | `template_rag_answer` | Always (if answer exists) | LLM answer + source footnote |
| 2 | `template_sensor_card` | `UPDATE` or `SYSTEM` intent + sensor data present | Markdown table: pH / EC / Temp / OD / Light with status icons |
| 3 | `template_prediction` | Any intent + `ml_outputs["growth_prediction"]` present | 60-minute forecast table |
| 4 | `template_harvest_card` | `HARVEST` intent + ml_outputs present | 3-scenario harvest timing card |
| 5 | `template_alert` | `SYSTEM` intent or `ml_outputs["anomaly_flag"]` set | INFO / WARNING / CRITICAL banner |

## Sensor thresholds (`_SENSOR_CFG`)
Each sensor key maps to `(label, unit, ok_range, warn_range)`:
- **Green ✅** = value inside `ok_range`
- **Amber ⚠️** = value inside `warn_range` but outside `ok_range`
- **Red 🔴** = outside both ranges → auto-generates a CRITICAL alert

Sensors tracked: pH, EC, Temperature, OD680, Water Level, Light.

## Alert auto-detection
`_alert_level_from_sensors(sensor)` scans all sensor readings and generates alert dicts for any out-of-range values. These are rendered as alert banners before the LLM answer.

## Output structure
Parts are joined with `---` dividers. Order:
1. Alert banners (if SYSTEM intent or anomaly)
2. Sensor card (if UPDATE/SYSTEM + sensor data)
3. Harvest card (if HARVEST + ml_outputs)
4. Prediction card (if ml_outputs has growth_prediction)
5. LLM answer with source footnote
6. **No-container tip** (edge case 2) — if `has_container=False` AND intent is `UPDATE`, `HARVEST`, or `SYSTEM`, a one-line italic tip is appended: *"No container linked. Enter your Container ID to enable sensor monitoring, ML predictions, and container control."*

## Dependencies
- `datetime` (timestamp display)
- `re` (source filename extraction from RAG context string)
