"use client";
import { useState, useEffect, useCallback } from "react";
import { useTheme } from "@/lib/ThemeContext";
import ConversationSidebar from "@/components/ConversationSidebar";
import AgentChat           from "@/components/chat/AgentChat";
import DashboardPage       from "@/components/dashboard/DashboardPage";
import AlertsPage          from "@/components/alerts/AlertsPage";
import ModelsPage          from "@/components/models/ModelsPage";
import { Dot }             from "@/components/atoms";
import {
  listConversations,
  deleteConversation,
  connectAlerts,
  getSensorData,
} from "@/lib/api";

// In production these come from auth / session
const USER_ID      = "demo-user";
const CONTAINER_ID = "container-01";

/* ── Pro page tab strip ─────────────────────────────────────────────────── */
const PRO_PAGES = [
  { k: "chat",      label: "Agent Chat", icon: "◎" },
  { k: "dashboard", label: "Dashboard",  icon: "▦" },
  { k: "alerts",    label: "Alerts",     icon: "△" },
  { k: "models",    label: "ML Models",  icon: "⬡" },
];

function ProTabBar({ page, setPage, alertCount }) {
  const { C } = useTheme();
  return (
    <div style={{
      display: "flex", gap: 2, padding: "0 20px",
      background: C.surface, borderBottom: `1px solid ${C.border}`, flexShrink: 0,
    }}>
      {PRO_PAGES.map((p) => {
        const active = page === p.k;
        return (
          <button key={p.k} onClick={() => setPage(p.k)} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "11px 14px", background: "none", border: "none",
            borderBottom: active ? `2px solid ${C.green}` : "2px solid transparent",
            color: active ? C.green : C.text3,
            fontSize: 12.5, fontFamily: C.sans, fontWeight: active ? 600 : 400,
            cursor: "pointer", transition: "all .15s", marginBottom: -1,
          }}>
            <span style={{ fontSize: 13 }}>{p.icon}</span>
            {p.label}
            {p.k === "alerts" && alertCount > 0 && (
              <span style={{
                background: C.red, color: "#fff",
                fontSize: 9, fontWeight: 700, padding: "1px 5px",
                borderRadius: 99, fontFamily: C.mono, marginLeft: 2,
              }}>{alertCount}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ── Main header bar ────────────────────────────────────────────────────── */
function MainHeader({ tier, page, conversations, activeConvId, alertCount, sensorLive }) {
  const titles = { chat: null, dashboard: "Live Dashboard", alerts: "Alerts & Monitoring", models: "ML Models" };
  const title  = titles[page];
  const convTitle = conversations.find((c) => c.id === activeConvId)?.title;

  return (
    <div style={{
      height:       48,
      display:      "flex",
      alignItems:   "center",
      padding:      "0 20px",
      borderBottom: `1px solid ${C.border}`,
      background:   C.surface,
      flexShrink:   0,
      gap:          12,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {page === "chat" ? (
          activeConvId && convTitle ? (
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
              {convTitle}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: C.text3, fontFamily: C.mono }}>New conversation</div>
          )
        ) : (
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{title}</div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {tier === "pro" && (
          <>
            {sensorLive && (
              <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 8.5, fontFamily: C.mono, color: C.text3 }}>
                <Dot size={5} blink />
                MQTT LIVE
              </div>
            )}
            {alertCount > 0 && (
              <div style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "3px 10px", borderRadius: 20,
                background: C.redSoft, border: "1px solid #4A1010",
                fontSize: 8.5, fontWeight: 700, color: C.red, fontFamily: C.mono,
              }}>
                <Dot color={C.red} size={5} blink />
                {alertCount} ALERT{alertCount > 1 ? "S" : ""}
              </div>
            )}
            <Pill label="PRO" color={C.green} />
          </>
        )}
        {tier === "free" && <Pill label="FREE" color={C.text3} />}
      </div>
    </div>
  );
}

function Pill({ label, color }) {
  return (
    <span style={{
      fontSize: 8.5, fontFamily: C.mono, fontWeight: 600,
      letterSpacing: 0.6, padding: "2px 7px", borderRadius: 4,
      background: color + "18", color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  );
}

/* ── App shell ──────────────────────────────────────────────────────────── */
export default function SpirulinaApp() {
  const [tier,           setTier]           = useState("free");
  const [proPage,        setProPage]        = useState("chat");
  const [conversations,  setConversations]  = useState([]);
  const [activeConvId,   setActiveConvId]   = useState(null);
  const [chatAlerts,     setChatAlerts]     = useState([]);
  const [allAlerts,      setAllAlerts]      = useState([]);
  const [sensorData,     setSensorData]     = useState(null);

  const page = tier === "pro" ? proPage : "chat";

  /* ── Load conversation list ───────────────────────────────────────────── */
  const refreshConversations = useCallback(async () => {
    const list = await listConversations(USER_ID);
    setConversations(list);
  }, []);

  useEffect(() => { refreshConversations(); }, [refreshConversations]);

  /* ── Sensor polling (Pro only) ────────────────────────────────────────── */
  useEffect(() => {
    if (tier !== "pro") return;
    let cancelled = false;
    const poll = async () => {
      const data = await getSensorData(CONTAINER_ID);
      if (!cancelled && data) setSensorData(data);
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [tier]);

  /* ── SSE alerts (Pro only) ───────────────────────────────────────────── */
  useEffect(() => {
    if (tier !== "pro") return;
    const now = () => new Date().toTimeString().slice(0, 5);
    const disconnect = connectAlerts(USER_ID, CONTAINER_ID, {
      onAlert: (text) => {
        const entry = { text, time: now(), severity: "medium" };
        setAllAlerts  ((a) => [...a, entry]);
        setChatAlerts ((a) => [...a, entry]);
      },
    });
    return disconnect;
  }, [tier]);

  /* ── Conversation handlers ────────────────────────────────────────────── */
  const handleNewChat = () => {
    setActiveConvId(null);
    if (tier === "pro") setProPage("chat");
  };

  const handleSelectConv = (id) => {
    setActiveConvId(id);
    if (tier === "pro") setProPage("chat");
  };

  const handleDeleteConv = async (id) => {
    await deleteConversation(USER_ID, id);
    if (activeConvId === id) setActiveConvId(null);
    await refreshConversations();
  };

  const handleConversationCreated = useCallback(async (id) => {
    setActiveConvId(id);
    await refreshConversations();
  }, [refreshConversations]);

  const handleMessageSent = useCallback(async () => {
    await refreshConversations();
  }, [refreshConversations]);

  const activeAlerts = allAlerts.filter((a) => a.severity === "critical" || a.severity === "medium");

  /* ── Layout ─────────────────────────────────────────────────────────── */
  return (
    <div style={{
      display:    "flex",
      height:     "100vh",
      width:      "100vw",
      background: C.bg,
      fontFamily: C.sans,
      overflow:   "hidden",
    }}>

      {/* ── Left: conversation sidebar ─────────────────────────────────── */}
      <ConversationSidebar
        userId={USER_ID}
        conversations={conversations}
        activeConvId={activeConvId}
        tier={tier}
        onNewChat={handleNewChat}
        onSelectConv={handleSelectConv}
        onDeleteConv={handleDeleteConv}
        onTierChange={(t) => { setTier(t); if (t === "free") setProPage("chat"); }}
      />

      {/* ── Right: main content ────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, height: "100vh" }}>

        {/* Pro tab strip */}
        {tier === "pro" && (
          <ProTabBar
            page={proPage}
            setPage={setProPage}
            alertCount={activeAlerts.length}
          />
        )}

        {/* Header bar */}
        <MainHeader
          tier={tier}
          page={page}
          conversations={conversations}
          activeConvId={activeConvId}
          alertCount={activeAlerts.length}
          sensorLive={!!sensorData}
        />

        {/* Page content */}
        {page === "chat" && (
          <AgentChat
            key={activeConvId ?? "new"}
            userId={USER_ID}
            containerId={CONTAINER_ID}
            tier={tier}
            conversationId={activeConvId}
            incomingAlerts={chatAlerts}
            onConversationCreated={handleConversationCreated}
            onMessageSent={handleMessageSent}
          />
        )}

        {page === "dashboard" && (
          <div style={{ flex: 1, overflow: "auto" }}>
            <DashboardPage sensorData={sensorData} />
          </div>
        )}

        {page === "alerts" && (
          <div style={{ flex: 1, overflow: "auto" }}>
            <AlertsPage
              alerts={allAlerts}
              onGoChat={() => setProPage("chat")}
            />
          </div>
        )}

        {page === "models" && (
          <div style={{ flex: 1, overflow: "auto" }}>
            <ModelsPage containerId={CONTAINER_ID} />
          </div>
        )}
      </div>
    </div>
  );
}
