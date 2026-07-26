"use client";
import { useState, useEffect, useRef } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { AgentAvatar, SpinnerDots } from "@/components/atoms";
import Bubble from "@/components/chat/Bubble";
import { sendMessage, getConversationMessages } from "@/lib/api";

export default function AgentChat({
  userId,
  containerId,
  tier,
  conversationId      = null,
  incomingAlerts      = [],
  onConversationCreated,
  onMessageSent,
  pendingQuestion     = null,
  onPendingQuestionConsumed,
}) {
  const { C } = useTheme();
  const [messages,   setMessages]   = useState([]);
  const [input,      setInput]      = useState("");
  const [thinking,   setThinking]   = useState(false);
  const [activeConv, setActiveConv] = useState(conversationId);

  const bottomRef      = useRef(null);
  const idRef          = useRef(1);
  const prevAlertCount = useRef(0);
  const textareaRef    = useRef(null);

  const now = () => new Date().toTimeString().slice(0, 5);

  /* Load history */
  useEffect(() => {
    setMessages([]);
    setActiveConv(conversationId);
    if (!conversationId) return;
    getConversationMessages(userId, conversationId).then((history) => {
      setMessages(history.map((m) => ({
        id:      idRef.current++,
        role:    m.role === "assistant" ? "agent" : "user",
        text:    m.content,
        content: { type: "text", text: m.content },
        time:    "",
      })));
    });
  }, [conversationId, userId]);

  /* SSE alerts */
  useEffect(() => {
    if (incomingAlerts.length <= prevAlertCount.current) return;
    const newAlerts = incomingAlerts.slice(prevAlertCount.current);
    prevAlertCount.current = incomingAlerts.length;
    setMessages((m) => [
      ...m,
      ...newAlerts.map((a) => ({ id: idRef.current++, role: "alert", text: a.text, time: a.time })),
    ]);
  }, [incomingAlerts]);

  /* Auto-scroll */
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking]);

  /* "Ask the assistant" from the Alerts page -- fire instantly, no typing */
  useEffect(() => {
    if (!pendingQuestion?.text) return;
    send(pendingQuestion.text);
    onPendingQuestionConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion?.id]);

  /* Send */
  const send = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || thinking) return;
    const t = now();
    setMessages((m) => [...m, { id: idRef.current++, role: "user", text, time: t }]);
    setInput("");
    if (textareaRef.current) { textareaRef.current.style.height = "auto"; }
    setThinking(true);
    try {
      const res = await sendMessage({ message: text, userId, containerId, tier, conversationId: activeConv || "" });
      if (!activeConv && res.conversation_id) {
        setActiveConv(res.conversation_id);
        onConversationCreated?.(res.conversation_id);
      } else {
        onMessageSent?.();
      }
      setMessages((m) => [...m, {
        id: idRef.current++, role: "agent",
        text: res.response,
        content:    res.content    || { type: "text", text: res.response },
        tools:      res.tools_used || [],
        tool_calls: res.tool_calls || [],
        plan:       res.plan       || "",
        time: t,
      }]);
    } catch (err) {
      const isLimit = err?.status === 429;
      const msg     = isLimit
        ? "You have reached the **3-message limit** for free accounts.\n\nAsk your admin to upgrade your account to **Pro** for unlimited access."
        : "Something went wrong. Please try again.";
      setMessages((m) => [...m, {
        id: idRef.current++, role: "agent",
        text: msg,
        content: { type: "text", text: msg },
        tools: [], tool_calls: [], plan: "", time: t,
      }]);
    } finally {
      setThinking(false);
    }
  };

  /* Empty-state prompts */
  const prompts = tier === "pro"
    ? ["My pH dropped to 8.1 overnight", "Should I harvest today?", "Culture turned pale yellow", "Adjust my EC to 2.5 mS/cm", "Run a full diagnosis"]
    : ["What pH should I target?", "How often to renew the medium?", "Signs of contamination", "Optimal temperature range", "What is Zarrouk medium?"];

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0, background: C.bg }}>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 0" }}>
        <div style={{ maxWidth: 720, width: "100%", margin: "0 auto", padding: "0 20px", display: "flex", flexDirection: "column", gap: 14 }}>

          {messages.length === 0 && !thinking && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 60, gap: 24 }}>
              <div style={{
                width: 48, height: 48, borderRadius: 14,
                background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
                display: "flex", alignItems: "center", justifyContent: "center",
                boxShadow: C.glowMd, animation: "pulse-glow 3s ease-in-out infinite",
              }}>
                <svg viewBox="0 0 14 14" fill="none" width={24} height={24}>
                  <path d="M7 .6C4.2.6 2.3 2.5 2.3 4.5c0 3 4.7 8.9 4.7 8.9s4.7-5.9 4.7-8.9C11.7 2.5 9.8.6 7 .6z" fill={C.green} />
                  <circle cx="7" cy="4.5" r="1.9" fill={C.bg} />
                </svg>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 22, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  How can I help?
                </div>
                <div style={{ fontSize: 12, color: C.text3, fontFamily: C.mono }}>
                  {tier === "pro" ? "Agent · Sensors · Anomaly Detector" : "Knowledge mode"}
                </div>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 520 }}>
                {prompts.map((p) => (
                  <button key={p} onClick={() => setInput(p)} style={{
                    padding: "8px 14px", borderRadius: 8,
                    background: C.card, border: `1px solid ${C.border}`,
                    color: C.text2, fontSize: 13, cursor: "pointer", transition: "all .15s",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.green; e.currentTarget.style.color = C.text; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.text2; }}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => <Bubble key={m.id} msg={m} />)}

          {thinking && (
            <div className="msg-enter" style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <AgentAvatar />
              <SpinnerDots />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div style={{ borderTop: `1px solid ${C.border}`, background: C.surface, flexShrink: 0, padding: "12px 20px 16px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <div style={{
            display: "flex", gap: 10, alignItems: "flex-end",
            background: C.card, border: `1px solid ${C.border2}`,
            borderRadius: 12, padding: "10px 14px",
            boxShadow: C.cardShadow, transition: "border-color .2s",
          }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 150) + "px";
              }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={`Ask about your ${tier === "pro" ? "batch, sensors, harvest…" : "spirulina cultivation…"}`}
              rows={1}
              style={{
                flex: 1, background: "transparent", border: "none",
                resize: "none", fontSize: 13.5, color: C.text,
                fontFamily: C.sans, lineHeight: 1.55,
                minHeight: 22, maxHeight: 150, overflowY: "auto",
              }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, paddingBottom: 1 }}>
              {input && (
                <span style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>⏎ send · shift+⏎ newline</span>
              )}
              <button onClick={send} disabled={!input.trim() || thinking} style={{
                width: 32, height: 32, borderRadius: 8, border: "none",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all .15s", flexShrink: 0,
                background:   input.trim() && !thinking ? C.green     : C.card2,
                color:        input.trim() && !thinking ? C.bg        : C.text3,
                opacity:      !input.trim() || thinking ? 0.5 : 1,
              }}>
                {thinking
                  ? <div style={{ width: 12, height: 12, borderRadius: "50%", border: `2px solid ${C.text3}`, borderTopColor: C.green, animation: "spin .75s linear infinite" }} />
                  : <svg width={14} height={14} viewBox="0 0 14 14" fill="none"><path d="M7 1L7 13M7 1L3 5M7 1L11 5" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"/></svg>
                }
              </button>
            </div>
          </div>
          <div style={{ fontSize: 10, color: C.text3, textAlign: "center", marginTop: 7, fontFamily: C.mono }}>
            {tier === "pro" ? "M1 Anomaly Detector · RAG · Live sensors" : "Knowledge mode — upgrade to Pro for sensor monitoring + ML"}
          </div>
        </div>
      </div>
    </div>
  );
}
