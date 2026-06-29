"use client";
import { useState, useRef, useEffect } from "react";
import { C } from "@/lib/theme";
import { sendMessage } from "@/lib/api";

export default function FreeTier({ onUpgrade }) {
  const [messages, setMessages] = useState([
    { r: "ai",   t: "Hello! I'm SpirulinaAI. Ask me anything about spirulina cultivation — pH management, nutrients, harvest timing, contamination, and more.", src: null },
  ]);
  const [input, setInput]     = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async () => {
    const text = input.trim();
    if (!text || thinking) return;
    setMessages((m) => [...m, { r: "user", t: text }]);
    setInput("");
    setThinking(true);
    try {
      const res = await sendMessage({ message: text, userId: "free-user", containerId: "", tier: "free" });
      const answer = res.content?.text || res.response || "I couldn't find an answer. Please try rephrasing.";
      setMessages((m) => [...m, { r: "ai", t: answer }]);
    } catch {
      setMessages((m) => [...m, { r: "ai", t: "Something went wrong. Please try again." }]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#F9F8F5", fontFamily: C.sans, color: "#2D3A2A" }}>
      {/* Header */}
      <div style={{ padding: "13px 16px", borderBottom: "1px solid #E8E4DC", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#fff" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: "linear-gradient(140deg,#3A7D4A,#5CAE6A)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg viewBox="0 0 12 12" fill="none" width={13} height={13}>
              <path d="M6 .5C3.5.5 2 2.2 2 4c0 2.5 4 7.5 4 7.5s4-5 4-7.5C10 2.2 8.5.5 6 .5z" fill="#fff" />
              <circle cx="6" cy="4" r="1.6" fill="#3A7D4A" />
            </svg>
          </div>
          <span style={{ fontFamily: C.serif, fontSize: 16, fontStyle: "italic", color: "#2D3A2A" }}>SpirulinaAI</span>
          <span style={{ fontSize: 8.5, fontFamily: C.mono, padding: "2px 7px", borderRadius: 20, background: "#F0EDE4", color: "#8A8474", fontWeight: 600 }}>FREE</span>
        </div>
        <button onClick={onUpgrade} style={{ fontSize: 11, padding: "6px 16px", borderRadius: 20, background: "#2D5A3A", color: "#C8EED0", border: "none", fontWeight: 700 }}>
          Upgrade to Pro →
        </button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 9 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.r === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ maxWidth: "84%", padding: "9px 12px", borderRadius: m.r === "user" ? "12px 12px 3px 12px" : "12px 12px 12px 3px", background: m.r === "user" ? "#2D5A3A" : "#fff", color: m.r === "user" ? "#E8F5E0" : "#3A3A2A", fontSize: 12, lineHeight: 1.55, border: m.r === "ai" ? "1px solid #E8E4DC" : "none" }}>
              {m.r === "ai" && (
                <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: 1, color: "#5CAE6A", marginBottom: 3, fontFamily: C.mono }}>
                  SPIRULINA AI <span style={{ background: "#F5F2EB", color: "#9A9282", padding: "1px 5px", borderRadius: 3 }}>RAG</span>
                </div>
              )}
              {m.t}
            </div>
          </div>
        ))}
        {thinking && (
          <div style={{ display: "flex", gap: 4, padding: "9px 12px", background: "#fff", border: "1px solid #E8E4DC", borderRadius: "12px 12px 12px 3px", width: "fit-content" }}>
            {[0,1,2].map(i => <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: "#5CAE6A", animation: `blink 1.1s ${i*0.18}s infinite` }} />)}
          </div>
        )}

        {/* Lock gate */}
        <div style={{ margin: "4px auto", width: "92%", background: "linear-gradient(135deg,#F7F5EE,#EDE9DC)", border: "1.5px dashed #C9C3B0", borderRadius: 14, padding: 16, textAlign: "center" }}>
          <div style={{ fontSize: 22, marginBottom: 5 }}>🔒</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#5A5240", marginBottom: 4 }}>Sensor access requires Pro</div>
          <div style={{ fontSize: 11, color: "#8A8274", lineHeight: 1.55, marginBottom: 10 }}>
            Free tier answers from the knowledge base only. Pro connects to your live MQTT sensors and the anomaly detector.
          </div>
          <div style={{ display: "flex", gap: 5, justifyContent: "center", flexWrap: "wrap", marginBottom: 10 }}>
            {["Anomaly Detector", "Live MQTT", "Rule + ML Alerts"].map((f, i) => (
              <span key={i} style={{ fontSize: 8.5, padding: "3px 8px", borderRadius: 20, background: "#E8E4D8", color: "#6A6252" }}>{f}</span>
            ))}
          </div>
          <button onClick={onUpgrade} style={{ fontSize: 11, padding: "7px 22px", borderRadius: 20, background: "#2D5A3A", color: "#C8EED0", border: "none", fontWeight: 700 }}>
            Unlock the full agent →
          </button>
        </div>
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "11px 13px", borderTop: "1px solid #E8E4DC", background: "#fff" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about spirulina cultivation…"
            style={{ flex: 1, padding: "9px 13px", borderRadius: 10, border: "1px solid #E0DDD4", fontSize: 12, color: "#2D3A2A", background: "#FAFAF7", outline: "none" }}
          />
          <button onClick={send} disabled={!input.trim() || thinking} style={{ width: 33, height: 33, borderRadius: "50%", background: "#2D5A3A", display: "flex", alignItems: "center", justifyContent: "center", color: "#C8EED0", fontSize: 15, border: "none", opacity: input.trim() && !thinking ? 1 : 0.5 }}>
            ↑
          </button>
        </div>
        <div style={{ fontSize: 8.5, color: "#B0A898", textAlign: "center", marginTop: 5, fontFamily: C.mono }}>Knowledge-only · RAG · no sensor access</div>
      </div>
    </div>
  );
}
