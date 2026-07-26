"use client";
import { useState, useEffect, useRef } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { Tag, Label, Dot } from "@/components/atoms";
import { getModelOutputs, predictCPC, predictSpecies } from "@/lib/api";


const LiveRow = ({ k, v, color }) => {
  const { C } = useTheme();
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
      <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono }}>{k}</span>
      <span style={{ fontSize: 10, fontWeight: 700, fontFamily: C.mono, color: color || C.text }}>{v}</span>
    </div>
  );
};

function LiveOutput({ data, error, loading }) {
  const { C } = useTheme();
  const box = { background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 7, padding: "10px 12px" };
  if (loading)  return <div style={{ ...box, color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Running…</div>;
  if (error)    return <div style={{ ...box, border: "1px solid #4A1010", color: C.red, fontFamily: C.mono, fontSize: 9 }}>{error}</div>;
  if (!data)    return <div style={{ ...box, color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Waiting for sensor data…</div>;
  return <div style={box}>{data}</div>;
}

/* ── CPC Image Predictor card ─────────────────────────────────────────────── */
function CPCPredictorCard() {
  const { C } = useTheme();
  const [file,     setFile]     = useState(null);
  const [preview,  setPreview]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFile = (f) => {
    if (!f || !f.type.startsWith("image/")) return;
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
  };

  const clear = () => {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  const handlePredict = async () => {
    if (!file || loading) return;
    setLoading(true);
    setError(null);
    try {
      const data = await predictCPC(file);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const cpcColor  = result ? (result.in_training_range ? C.green : C.amber) : C.text3;
  const resultTag = result ? (result.in_training_range ? "IN RANGE" : "OUT OF RANGE") : null;

  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
        <div style={{
          width: 34, height: 34, borderRadius: 8,
          background: C.greenSoft,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 9, fontWeight: 800, fontFamily: C.mono, color: C.green, flexShrink: 0,
          letterSpacing: 0.5,
        }}>CPC</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>CPC Predictor</div>
          <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>
            Image-based biomass estimation · CNN encoder + XGBoost · R²=0.988
          </div>
        </div>
        {resultTag && <Tag color={result.in_training_range ? C.green : C.amber}>{resultTag}</Tag>}
      </div>

      {/* Body */}
      <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>

        {/* Left: drop zone */}
        <div>
          <Label>SPIRULINA IMAGE</Label>
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e)  => { e.preventDefault(); setDragging(true); }}
            onDragLeave={()  => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
            style={{
              border:       `1.5px dashed ${dragging ? C.green : preview ? C.border2 : C.border}`,
              borderRadius: 8,
              background:   dragging ? C.greenAlpha8 : C.card2,
              cursor:       "pointer",
              display:      "flex",
              alignItems:   "center",
              justifyContent: "center",
              flexDirection: "column",
              gap:          6,
              minHeight:    110,
              overflow:     "hidden",
              transition:   "border-color 0.15s, background 0.15s",
              padding:      preview ? 0 : "18px 10px",
            }}
          >
            {preview ? (
              <img
                src={preview}
                alt="preview"
                style={{ width: "100%", height: 110, objectFit: "cover", display: "block" }}
              />
            ) : (
              <>
                <span style={{ fontSize: 22, opacity: 0.7 }}>&#128300;</span>
                <span style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, textAlign: "center" }}>
                  Drop image or click to browse
                </span>
                <span style={{ fontSize: 8, color: C.text3, fontFamily: C.mono }}>JPEG · PNG · BMP</span>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => handleFile(e.target.files[0])}
          />
          {preview && (
            <div
              onClick={() => inputRef.current?.click()}
              style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, marginTop: 4, cursor: "pointer",
                       overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {file?.name} — click to change
            </div>
          )}
        </div>

        {/* Right: result */}
        <div>
          <Label>PREDICTION</Label>
          <div style={{
            background: C.card2, border: `1px solid ${C.border2}`,
            borderRadius: 7, padding: "10px 12px", minHeight: 110,
            display: "flex", flexDirection: "column", justifyContent: "center",
          }}>
            {loading ? (
              <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Running model…</div>
            ) : error ? (
              <div style={{ color: C.red, fontFamily: C.mono, fontSize: 9, wordBreak: "break-word" }}>{error}</div>
            ) : result ? (
              <>
                <div style={{ fontSize: 30, fontWeight: 800, fontFamily: C.mono, color: cpcColor, lineHeight: 1 }}>
                  {result.cpc_mgml.toFixed(4)}
                </div>
                <div style={{ fontSize: 9.5, color: C.text2, fontFamily: C.mono, marginTop: 3 }}>
                  mg/mL CPC concentration
                </div>
                <div style={{ marginTop: 9, display: "flex", flexDirection: "column", gap: 3 }}>
                  <span style={{
                    fontSize: 8, borderRadius: 4, padding: "2px 6px", fontFamily: C.mono,
                    background: result.in_training_range ? C.greenSoft : C.amberSoft,
                    border: `1px solid ${result.in_training_range ? C.green + "30" : C.amber + "30"}`,
                    color: result.in_training_range ? C.green : C.amber,
                    alignSelf: "flex-start",
                  }}>
                    {result.in_training_range ? "within training range" : "outside training range — treat with caution"}
                  </span>
                  <span style={{
                    fontSize: 8, background: C.card, border: `1px solid ${C.border}`,
                    borderRadius: 4, padding: "2px 6px", color: C.text3, fontFamily: C.mono,
                    alignSelf: "flex-start",
                  }}>
                    training range: {result.training_range.min} – {result.training_range.max} mg/mL
                  </span>
                </div>
              </>
            ) : (
              <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 9 }}>
                Upload a spirulina image and click Predict
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer: predict + clear buttons */}
      <div style={{
        padding: "10px 15px", borderTop: `1px solid ${C.border}`,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <button
          disabled={!file || loading}
          onClick={handlePredict}
          style={{
            padding:    "7px 18px",
            borderRadius: 7,
            background: file && !loading ? C.green : C.card2,
            color:      file && !loading ? "#000"  : C.text3,
            border:     "none",
            fontFamily: C.mono,
            fontSize:   10.5,
            fontWeight: 700,
            cursor:     file && !loading ? "pointer" : "not-allowed",
            transition: "background 0.15s, color 0.15s",
          }}
        >
          {loading ? "Predicting…" : "Predict CPC"}
        </button>

        {(result || preview) && !loading && (
          <button
            onClick={clear}
            style={{
              padding: "7px 12px", borderRadius: 7,
              background: "none", color: C.text3,
              border: `1px solid ${C.border}`,
              fontFamily: C.mono, fontSize: 10, cursor: "pointer",
            }}
          >
            Clear
          </button>
        )}

        <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono, marginLeft: "auto" }}>
          random-split R²=0.988 · MAE=0.006 mg/mL
        </span>
      </div>
    </div>
  );
}


/* ── Species Classifier card ──────────────────────────────────────────────── */
function SpeciesClassifierCard() {
  const { C } = useTheme();
  const [file,     setFile]     = useState(null);
  const [preview,  setPreview]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFile = (f) => {
    if (!f || !f.type.startsWith("image/")) return;
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
  };

  const clear = () => {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  const handlePredict = async () => {
    if (!file || loading) return;
    setLoading(true);
    setError(null);
    try {
      const data = await predictSpecies(file);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const resultColor = result ? (result.is_target_species ? C.green : C.red) : C.text3;
  const resultTag   = result ? (result.is_target_species ? "TARGET SPECIES" : "CONTAMINATION") : null;

  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
        <div style={{
          width: 34, height: 34, borderRadius: 8,
          background: C.greenSoft,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 9, fontWeight: 800, fontFamily: C.mono, color: C.green, flexShrink: 0,
          letterSpacing: 0.5,
        }}>SPC</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Species Classifier</div>
          <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>
            Contamination check · shape/texture features + XGBoost · ~97% test accuracy
          </div>
        </div>
        {resultTag && <Tag color={resultColor}>{resultTag}</Tag>}
      </div>

      {/* Body */}
      <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>

        {/* Left: drop zone */}
        <div>
          <Label>MICROSCOPE IMAGE</Label>
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e)  => { e.preventDefault(); setDragging(true); }}
            onDragLeave={()  => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
            style={{
              border:       `1.5px dashed ${dragging ? C.green : preview ? C.border2 : C.border}`,
              borderRadius: 8,
              background:   dragging ? C.greenAlpha8 : C.card2,
              cursor:       "pointer",
              display:      "flex",
              alignItems:   "center",
              justifyContent: "center",
              flexDirection: "column",
              gap:          6,
              minHeight:    110,
              overflow:     "hidden",
              transition:   "border-color 0.15s, background 0.15s",
              padding:      preview ? 0 : "18px 10px",
            }}
          >
            {preview ? (
              <img
                src={preview}
                alt="preview"
                style={{ width: "100%", height: 110, objectFit: "cover", display: "block" }}
              />
            ) : (
              <>
                <span style={{ fontSize: 22, opacity: 0.7 }}>&#128300;</span>
                <span style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, textAlign: "center" }}>
                  Drop image or click to browse
                </span>
                <span style={{ fontSize: 8, color: C.text3, fontFamily: C.mono }}>JPEG · PNG · BMP</span>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => handleFile(e.target.files[0])}
          />
          {preview && (
            <div
              onClick={() => inputRef.current?.click()}
              style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, marginTop: 4, cursor: "pointer",
                       overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {file?.name} — click to change
            </div>
          )}
        </div>

        {/* Right: result */}
        <div>
          <Label>PREDICTION</Label>
          <div style={{
            background: C.card2, border: `1px solid ${C.border2}`,
            borderRadius: 7, padding: "10px 12px", minHeight: 110,
            display: "flex", flexDirection: "column", justifyContent: "center",
          }}>
            {loading ? (
              <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Running model…</div>
            ) : error ? (
              <div style={{ color: C.red, fontFamily: C.mono, fontSize: 9, wordBreak: "break-word" }}>{error}</div>
            ) : result ? (
              <>
                <div style={{ fontSize: 16, fontWeight: 800, fontFamily: C.mono, color: resultColor, lineHeight: 1.3 }}>
                  {result.species.replace(/_/g, " ")}
                </div>
                <div style={{ fontSize: 9.5, color: C.text2, fontFamily: C.mono, marginTop: 3 }}>
                  confidence: {(result.confidence * 100).toFixed(1)}%
                </div>
                {result.warning && (
                  <div style={{
                    fontSize: 8.5, marginTop: 8, padding: "5px 8px", borderRadius: 5,
                    background: C.redSoft, border: "1px solid #4A1010", color: C.red, fontFamily: C.mono,
                  }}>
                    ⚠ {result.warning}
                  </div>
                )}
                <div style={{ marginTop: 9, display: "flex", flexDirection: "column", gap: 3 }}>
                  {Object.entries(result.probabilities)
                    .sort((a, b) => b[1] - a[1])
                    .map(([cls, p]) => (
                      <div key={cls} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ fontSize: 8, color: C.text3, fontFamily: C.mono }}>{cls.replace(/_/g, " ")}</span>
                        <span style={{ fontSize: 8, color: C.text2, fontFamily: C.mono }}>{(p * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                </div>
              </>
            ) : (
              <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 9 }}>
                Upload a microalgae image and click Predict
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer: predict + clear buttons */}
      <div style={{
        padding: "10px 15px", borderTop: `1px solid ${C.border}`,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <button
          disabled={!file || loading}
          onClick={handlePredict}
          style={{
            padding:    "7px 18px",
            borderRadius: 7,
            background: file && !loading ? C.green : C.card2,
            color:      file && !loading ? "#000"  : C.text3,
            border:     "none",
            fontFamily: C.mono,
            fontSize:   10.5,
            fontWeight: 700,
            cursor:     file && !loading ? "pointer" : "not-allowed",
            transition: "background 0.15s, color 0.15s",
          }}
        >
          {loading ? "Predicting…" : "Predict Species"}
        </button>

        {(result || preview) && !loading && (
          <button
            onClick={clear}
            style={{
              padding: "7px 12px", borderRadius: 7,
              background: "none", color: C.text3,
              border: `1px solid ${C.border}`,
              fontFamily: C.mono, fontSize: 10, cursor: "pointer",
            }}
          >
            Clear
          </button>
        )}

        <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono, marginLeft: "auto" }}>
          Chlamydomonas · Chlorella · Spirulina
        </span>
      </div>
    </div>
  );
}


/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function ModelsPage({ containerId }) {
  const { C } = useTheme();
  const [outputs, setOutputs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => {
    if (!containerId) return;
    let cancelled = false;

    const poll = async () => {
      const data = await getModelOutputs(containerId);
      if (cancelled) return;
      setOutputs(data);
      setLoading(false);
      if (data && !data.error) setLastRun(new Date().toTimeString().slice(0, 8));
    };

    poll();
    const id = setInterval(poll, 15_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [containerId]);

  const m1 = outputs?.m1 || {};

  const m1Color = m1.anomaly ? C.red : C.green;
  const m1Tag   = m1.error ? "ERROR" : m1.anomaly ? "ANOMALY" : m1.severity !== undefined ? "NORMAL" : "PENDING";
  const severityColor = m1.severity === "critical" ? C.red : m1.severity === "warning" ? C.amber : C.green;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 11 }}>

      {/* Status bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: 9 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, fontFamily: C.mono, color: C.text3 }}>
          <Dot size={5} blink={!loading} color={loading ? C.text3 : C.green} />
          {loading
            ? "Running models…"
            : outputs?.error === "no_data"
            ? "No sensor history yet — waiting for readings"
            : `Last run: ${lastRun}  ·  ${outputs?.readings ?? 0} readings`}
        </div>
        <span style={{ fontSize: 8.5, fontFamily: C.mono, color: C.text3 }}>auto-refresh 15s</span>
      </div>

      {/* M1 — Anomaly Detector */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.redSoft, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, fontFamily: C.mono, color: C.red, flexShrink: 0 }}>M1</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Anomaly Detector</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>Rule engine + seasonal check · LOF combination model (24h cron)</div>
          </div>
          <Tag color={m1.anomaly ? C.red : m1.error ? C.red : C.green}>{m1Tag}</Tag>
        </div>
        <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>INPUT FEATURES</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["pH","EC","DO","temperature","luminosity"].map((f) => (
                <span key={f} style={{ fontSize: 8.5, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 4, padding: "2px 6px", color: C.text2, fontFamily: C.mono }}>{f}</span>
              ))}
            </div>
          </div>
          <div>
            <Label>LIVE OUTPUT</Label>
            <LiveOutput error={m1.error} loading={loading} data={m1.severity !== undefined ? (
              <>
                <LiveRow k="anomaly"  v={m1.anomaly ? "YES" : "no"} color={m1Color} />
                <LiveRow k="severity" v={m1.severity || "ok"}       color={severityColor} />
                {(m1.rule_findings || []).map((f, i) => (
                  <LiveRow key={i} k={f.parameter} v={f.label} color={f.severity >= 3 ? C.red : C.amber} />
                ))}
              </>
            ) : null} />
          </div>
        </div>
      </div>

      {/* CPC Image Predictor */}
      <CPCPredictorCard />

      {/* Species Classifier */}
      <SpeciesClassifierCard />

    </div>
  );
}
