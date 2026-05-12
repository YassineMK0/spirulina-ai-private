"use client";
import { useState, useEffect, useRef } from "react";
import { C } from "@/lib/theme";
import { AgentAvatar, SpinnerDots } from "@/components/atoms";
import Bubble from "@/components/chat/Bubble";
import { sendMessage, getHistory } from "@/lib/api";

export default function AgentChat({ userId, containerId, tier, incomingAlerts = [] }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput]       = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef(null);
  const idRef     = useRef(1);
  const prevAlertCount = useRef(0);

  const now = () => new Date().toTimeString().slice(0, 5);

  // Load history on mount
  useEffect(() => {
    getHistory(userId).then((history) => {
      const loaded = history.map((m) => ({
        id:      idRef.current++,
        role:    m.role === "assistant" ? "agent" : "user",
        text:    m.content,
        content: { type: "text", text: m.content },
        time:    "",
      }));
      setMessages(loaded);
    });
  }, [userId]);

  // Inject SSE alerts from ProShell into the chat message list
  useEffect(() => {
    if (incomingAlerts.length <= prevAlertCount.current) return;
    const newAlerts = incomingAlerts.slice(prevAlertCount.current);
    prevAlertCount.current = incomingAlerts.length;
    setMessages((m) => [
      ...m,
      ...newAlerts.map((a) => ({ id: idRef.current++, role: "alert", text: a.text, time: a.time })),
    ]);
  }, [incomingAlerts]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async () => {
    const text = input.trim();
    if (!text || thinking) return;

    const t = now();
    setMessages((m) => [...m, { id: idRef.current++, role: "user", text, time: t }]);
    setInput("");
    setThinking(true);

    try {
      const res = await sendMessage({ message: text, userId, containerId, tier });
      setMessages((m) => [...m, {
        id:      idRef.current++,
        role:    "agent",
        text:    res.response,
        content: res.content || { type: "text", text: res.response },
        tools:   res.tools_used || [],
        time:    t,
      }]);
    } catch (err) {
      setMessages((m) => [...m, {
        id:      idRef.current++,
        role:    "agent",
        text:    "Something went wrong. Please try again.",
        content: { type: "text", text: "Something went wrong. Please try again." },
        tools:   [],
        time:    t,
      }]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 13 }}>
        {messages.length === 0 && !thinking && (
          <div style={{ textAlign: "center", marginTop: 40, color: C.text3, fontSize: 12, fontFamily: C.mono }}>
            Ask anything about your spirulina batch…
          </div>
        )}
        {messages.map((m) => <Bubble key={m.id} msg={m} />)}
        {thinking && (
          <div className="msg-enter" style={{ display: "flex", gap: 9, alignItems: "center" }}>
            <AgentAvatar />
            <SpinnerDots />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{ padding: "11px 16px", borderTop: `1px solid ${C.border}`, background: C.surface, flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, background: C.card, border: `1px solid ${C.border2}`, borderRadius: 10, padding: "9px 13px" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Ask about your batch, sensors, harvest, nutrition…"
              style={{ flex: 1, background: "transparent", border: "none", fontSize: 12, color: C.text, fontFamily: C.sans }}
            />
            {input && <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono, flexShrink: 0 }}>↵</span>}
          </div>
          <button
            onClick={send}
            disabled={!input.trim() || thinking}
            style={{
              width: 36, height: 36, borderRadius: 9, border: "none", fontSize: 15,
              display: "flex", alignItems: "center", justifyContent: "center", transition: "all .15s", flexShrink: 0,
              background: input.trim() && !thinking ? C.greenSoft : C.card,
              color:      input.trim() && !thinking ? C.green     : C.text3,
              outline:    input.trim() && !thinking ? `1px solid #234830` : `1px solid ${C.border}`,
            }}
          >
            {thinking
              ? <div style={{ width: 13, height: 13, borderRadius: "50%", border: `2px solid ${C.text3}`, borderTopColor: C.green, animation: "spin .75s linear infinite" }} />
              : "↑"
            }
          </button>
        </div>
        <div style={{ fontSize: 8.5, color: C.text3, textAlign: "center", marginTop: 6, fontFamily: C.mono }}>
          {tier === "pro"
            ? "M1 Anomaly · M2 Growth · M3 Harvest · RAG knowledge · Live sensors"
            : "Knowledge-only · RAG · no sensor access"}
        </div>
      </div>
    </div>
  );
}
