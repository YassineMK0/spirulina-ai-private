"use client";
import { useState, useEffect, useCallback } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { useAuth } from "@/lib/AuthContext";
import ConversationSidebar from "@/components/ConversationSidebar";
import AgentChat           from "@/components/chat/AgentChat";
import DashboardPage       from "@/components/dashboard/DashboardPage";
import AlertsPage          from "@/components/alerts/AlertsPage";
import ModelsPage          from "@/components/models/ModelsPage";
import AdminPage           from "@/components/admin/AdminPage";
import {
  listConversations, deleteConversation,
  connectAlerts, getSensorData, getAlertHistory,
} from "@/lib/api";

const CONTAINER_ID = "container-01";

// ── Shared top bar for admin layout ──────────────────────────────────────────
function AdminTopBar({ user, C, isDark, toggleTheme, logout }) {
  return (
    <div style={{
      height: 52, display: "flex", alignItems: "center",
      padding: "0 24px", borderBottom: `1px solid ${C.border}`,
      background: C.surface, flexShrink: 0, gap: 12,
    }}>
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 8,
          background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg viewBox="0 0 14 14" fill="none" width={15} height={15}>
            <path d="M7 .6C4.2.6 2.3 2.5 2.3 4.5c0 3 4.7 8.9 4.7 8.9s4.7-5.9 4.7-8.9C11.7 2.5 9.8.6 7 .6z" fill={C.green} />
            <circle cx="7" cy="4.5" r="1.9" fill={C.bg} />
          </svg>
        </div>
        <span style={{ fontSize: 14.5, fontWeight: 700, color: C.text, letterSpacing: -0.2 }}>SpirulinaAI</span>
      </div>

      <span style={{
        fontSize: 10.5, fontFamily: C.mono, fontWeight: 700,
        padding: "2px 9px", borderRadius: 5,
        background: `${C.teal}14`, color: C.teal, border: `1px solid ${C.teal}30`,
        letterSpacing: 0.5,
      }}>ADMIN</span>

      <div style={{ flex: 1 }} />

      {/* Theme toggle */}
      <button onClick={toggleTheme} title={isDark ? "Light mode" : "Dark mode"} style={{
        width: 30, height: 30, borderRadius: 7, background: C.card2,
        border: `1px solid ${C.border}`, color: C.text2, fontSize: 13,
        display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
      }}>
        {isDark ? "☀" : "☾"}
      </button>

      {/* User pill */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "4px 10px 4px 6px", borderRadius: 8,
        background: C.card, border: `1px solid ${C.border}`,
      }}>
        <div style={{
          width: 24, height: 24, borderRadius: 6,
          background: `${C.teal}18`, border: `1px solid ${C.teal}30`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 700, color: C.teal,
        }}>
          {user.email[0].toUpperCase()}
        </div>
        <span style={{ fontSize: 12.5, color: C.text2 }}>{user.email}</span>
      </div>

      {/* Logout */}
      <button onClick={logout} title="Sign out" style={{
        width: 30, height: 30, borderRadius: 7, background: "none",
        border: `1px solid ${C.border}`, color: C.text3, fontSize: 14,
        display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.color = C.red; e.currentTarget.style.background = C.redSoft; e.currentTarget.style.borderColor = `${C.red}50`; }}
      onMouseLeave={(e) => { e.currentTarget.style.color = C.text3; e.currentTarget.style.background = "none"; e.currentTarget.style.borderColor = C.border; }}
      >⏻</button>
    </div>
  );
}

// ── Pro tab bar ───────────────────────────────────────────────────────────────
const PRO_PAGES = [
  { k: "chat",      label: "Agent Chat", icon: "◎" },
  { k: "dashboard", label: "Dashboard",  icon: "▦" },
  { k: "alerts",    label: "Alerts",     icon: "△" },
  { k: "models",    label: "ML Models",  icon: "⬡" },
];

function ProTabBar({ page, setPage, alertCount, C }) {
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
                background: C.red, color: "#fff", fontSize: 9, fontWeight: 700,
                padding: "1px 5px", borderRadius: 99, fontFamily: C.mono, marginLeft: 2,
              }}>{alertCount}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Header bar (free + pro) ───────────────────────────────────────────────────
function MainHeader({ tier, page, conversations, activeConvId, alertCount, sensorLive, C }) {
  const titles = { chat: null, dashboard: "Live Dashboard", alerts: "Alerts & Monitoring", models: "ML Models" };
  const convTitle = conversations.find((c) => c.id === activeConvId)?.title;

  return (
    <div style={{
      height: 48, display: "flex", alignItems: "center",
      padding: "0 20px", borderBottom: `1px solid ${C.border}`,
      background: C.surface, flexShrink: 0, gap: 12,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {page === "chat"
          ? convTitle
            ? <div style={{ fontSize: 13.5, fontWeight: 500, color: C.text, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>{convTitle}</div>
            : <div style={{ fontSize: 13, color: C.text3 }}>New conversation</div>
          : <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{titles[page]}</div>
        }
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {tier === "pro" && sensorLive && (
          <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, fontFamily: C.mono, color: C.text3 }}>
            <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.green, animation: "blink 1.6s infinite" }} />
            MQTT
          </div>
        )}
        {alertCount > 0 && (
          <div style={{
            display: "flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 20,
            background: C.redSoft, border: `1px solid ${C.red}30`,
            fontSize: 10, fontWeight: 600, color: C.red, fontFamily: C.mono,
          }}>
            <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.red, animation: "blink 1.2s infinite" }} />
            {alertCount} alert{alertCount > 1 ? "s" : ""}
          </div>
        )}
        <span style={{
          fontSize: 10, fontFamily: C.mono, fontWeight: 600, padding: "2px 8px", borderRadius: 5,
          background: tier === "pro" ? `${C.green}14` : `${C.text3}14`,
          color:      tier === "pro" ? C.green         : C.text3,
          border: `1px solid ${tier === "pro" ? C.green + "30" : C.border}`,
        }}>
          {tier.toUpperCase()}
        </span>
      </div>
    </div>
  );
}

// ── Shared chat+sidebar state hook ────────────────────────────────────────────
function useChatState(userId, isPro) {
  const [proPage,       setProPage]       = useState("chat");
  const [conversations, setConversations] = useState([]);
  const [activeConvId,  setActiveConvId]  = useState(null);
  const [chatAlerts,    setChatAlerts]    = useState([]);
  const [allAlerts,     setAllAlerts]     = useState([]);
  const [sensorData,    setSensorData]    = useState(null);

  const refreshConversations = useCallback(async () => {
    setConversations(await listConversations(userId));
  }, [userId]);

  useEffect(() => { refreshConversations(); }, [refreshConversations]);

  useEffect(() => {
    if (!isPro) return;
    let cancelled = false;
    const poll = async () => { const d = await getSensorData(CONTAINER_ID); if (!cancelled && d) setSensorData(d); };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [isPro]);

  // Real detection time when the server supplies one (live SSE `created_at`,
  // or a history row's `created_at`); only falls back to "now" if it's ever
  // missing, instead of always fabricating a receipt-time timestamp.
  const formatTime = (iso) => (iso ? new Date(iso).toLocaleString() : new Date().toLocaleString());

  // Hydrate from persisted history on load — otherwise a page refresh loses
  // every alert that isn't still sitting in the live SSE stream.
  useEffect(() => {
    if (!isPro) return;
    let cancelled = false;
    (async () => {
      const rows = await getAlertHistory(userId, 50);
      if (cancelled || !rows.length) return;
      // DB returns newest-first; the UI expects oldest-first (last = most recent).
      const entries = [...rows].reverse().map((r) => ({
        id:       r.id,
        text:     r.message,
        time:     formatTime(r.created_at),
        severity: r.severity || "medium",
        affected: r.affected || [],
        source:   r.source   || "model",
      }));
      setAllAlerts((a) => [...entries, ...a]);
    })();
    return () => { cancelled = true; };
  }, [isPro, userId]);

  useEffect(() => {
    if (!isPro) return;
    return connectAlerts(userId, CONTAINER_ID, {
      onAlert: (text, meta) => {
        const entry = {
          text, time: formatTime(meta?.createdAt),
          severity: meta?.severity || "medium",
          affected: meta?.affected || [],
          source:   meta?.source   || "model",
        };
        setAllAlerts ((a) => [...a, entry]);
        setChatAlerts((a) => [...a, entry]);
      },
    });
  }, [isPro, userId]);

  const handleNewChat      = () => { setActiveConvId(null); if (isPro) setProPage("chat"); };
  const handleSelectConv   = (id) => { setActiveConvId(id); if (isPro) setProPage("chat"); };
  const handleDeleteConv   = async (id) => { await deleteConversation(userId, id); if (activeConvId === id) setActiveConvId(null); await refreshConversations(); };
  const handleConvCreated  = useCallback(async (id) => { setActiveConvId(id); await refreshConversations(); }, [refreshConversations]);
  const handleMessageSent  = useCallback(async () => { await refreshConversations(); }, [refreshConversations]);

  const activeAlerts = allAlerts.filter((a) => a.severity === "critical" || a.severity === "medium");

  return {
    proPage, setProPage,
    conversations, activeConvId,
    chatAlerts, allAlerts, activeAlerts,
    sensorData,
    handleNewChat, handleSelectConv, handleDeleteConv,
    handleConvCreated, handleMessageSent,
  };
}

// ═════════════════════════════════════════════════════════════════════════════
// Main app — branches on tier
// ═════════════════════════════════════════════════════════════════════════════
export default function SpirulinaApp({ user }) {
  const { C, isDark, toggleTheme } = useTheme();
  const { logout }                 = useAuth();
  const tier                       = user.tier;

  // ── ADMIN — only the admin dashboard ────────────────────────────────────
  if (tier === "admin") {
    return (
      <div style={{ height: "100vh", width: "100vw", background: C.bg, display: "flex", flexDirection: "column", overflow: "hidden", fontFamily: C.sans }}>
        <AdminTopBar user={user} C={C} isDark={isDark} toggleTheme={toggleTheme} logout={logout} />
        <div style={{ flex: 1, overflowY: "auto" }}>
          <AdminPage currentUserId={user.id} />
        </div>
      </div>
    );
  }

  // ── FREE + PRO — share sidebar + chat state ──────────────────────────────
  return <ChatApp user={user} tier={tier} C={C} logout={logout} />;
}

// ── ChatApp: used by both free and pro ────────────────────────────────────────
function ChatApp({ user, tier, C, logout }) {
  const isPro = tier === "pro";
  const {
    proPage, setProPage,
    conversations, activeConvId,
    chatAlerts, activeAlerts, sensorData,
    handleNewChat, handleSelectConv, handleDeleteConv,
    handleConvCreated, handleMessageSent,
  } = useChatState(user.id, isPro);

  const page = isPro ? proPage : "chat";

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw", background: C.bg, fontFamily: C.sans, overflow: "hidden" }}>

      {/* Sidebar */}
      <ConversationSidebar
        user={user}
        conversations={conversations}
        activeConvId={activeConvId}
        onNewChat={handleNewChat}
        onSelectConv={handleSelectConv}
        onDeleteConv={handleDeleteConv}
        onLogout={logout}
      />

      {/* Right panel */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, height: "100vh" }}>

        {/* Pro tab bar */}
        {isPro && (
          <ProTabBar page={proPage} setPage={setProPage} alertCount={activeAlerts.length} C={C} />
        )}

        {/* Header */}
        <MainHeader
          tier={tier} page={page}
          conversations={conversations} activeConvId={activeConvId}
          alertCount={activeAlerts.length} sensorLive={!!sensorData} C={C}
        />

        {/* Content */}
        {page === "chat" && (
          <AgentChat
            key={activeConvId ?? "new"}
            userId={user.id} containerId={CONTAINER_ID} tier={tier}
            conversationId={activeConvId}
            incomingAlerts={chatAlerts}
            onConversationCreated={handleConvCreated}
            onMessageSent={handleMessageSent}
          />
        )}
        {page === "dashboard" && <div style={{ flex: 1, overflow: "auto" }}><DashboardPage sensorData={sensorData} /></div>}
        {page === "alerts"    && <div style={{ flex: 1, overflow: "auto" }}><AlertsPage alerts={activeAlerts} onGoChat={() => setProPage("chat")} /></div>}
        {page === "models"    && <div style={{ flex: 1, overflow: "auto" }}><ModelsPage containerId={CONTAINER_ID} /></div>}
      </div>
    </div>
  );
}
