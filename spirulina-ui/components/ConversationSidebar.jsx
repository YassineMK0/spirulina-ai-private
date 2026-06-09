"use client";
import { useState } from "react";
import { useTheme } from "@/lib/ThemeContext";

function groupConversations(convs) {
  const startOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today     = startOf(new Date());
  const yesterday = today - 86_400_000;
  const weekAgo   = today - 7 * 86_400_000;
  const groups = { Today: [], Yesterday: [], "Last 7 days": [], Older: [] };
  for (const c of convs) {
    const t = new Date(c.updated_at || c.created_at).getTime();
    if      (t >= today)     groups.Today.push(c);
    else if (t >= yesterday) groups.Yesterday.push(c);
    else if (t >= weekAgo)   groups["Last 7 days"].push(c);
    else                     groups.Older.push(c);
  }
  return groups;
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso), now = new Date(), diff = now - d;
  if (diff < 60_000)    return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function ConvRow({ conv, isActive, onSelect, onDelete }) {
  const { C }                     = useTheme();
  const [hover,    setHover]      = useState(false);
  const [deleting, setDeleting]   = useState(false);

  return (
    <div
      onClick={() => onSelect(conv.id)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "7px 10px", borderRadius: 7, cursor: "pointer",
        background: isActive ? C.card : hover ? C.card2 : "transparent",
        borderLeft: isActive ? `2px solid ${C.green}` : "2px solid transparent",
        transition: "all .13s", marginBottom: 1,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: isActive ? 500 : 400, color: isActive ? C.text : C.text2,
          overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis",
        }}>
          {conv.title || "New conversation"}
        </div>
        <div style={{ fontSize: 10.5, color: C.text3, fontFamily: C.mono, marginTop: 2 }}>
          {formatTime(conv.updated_at)}
        </div>
      </div>
      {hover && !deleting && (
        <button
          onClick={(e) => { e.stopPropagation(); setDeleting(true); onDelete(conv.id); }}
          style={{
            width: 20, height: 20, borderRadius: 5, background: "none", border: "none",
            color: C.text3, fontSize: 14, display: "flex", alignItems: "center",
            justifyContent: "center", flexShrink: 0,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = C.red; e.currentTarget.style.background = C.redSoft; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = C.text3; e.currentTarget.style.background = "none"; }}
        >×</button>
      )}
    </div>
  );
}

export default function ConversationSidebar({
  user, conversations = [], activeConvId = null,
  onNewChat, onSelectConv, onDeleteConv, onLogout,
}) {
  const { C, isDark, toggleTheme } = useTheme();
  const groups  = groupConversations(conversations);
  const isEmpty = conversations.length === 0;

  const tierColor = user?.tier === "admin" ? C.teal : user?.tier === "pro" ? C.green : C.text3;
  const tierBg    = user?.tier === "admin" ? `${C.teal}14` : user?.tier === "pro" ? `${C.green}14` : `${C.text3}14`;

  return (
    <div style={{
      width: 256, flexShrink: 0, display: "flex", flexDirection: "column",
      height: "100vh", background: C.surface, borderRight: `1px solid ${C.border}`,
    }}>

      {/* Header */}
      <div style={{ padding: "16px 14px 12px", borderBottom: `1px solid ${C.border}` }}>
        {/* Logo row */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 9, flexShrink: 0,
            background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: C.glowSm,
          }}>
            <svg viewBox="0 0 14 14" fill="none" width={16} height={16}>
              <path d="M7 .6C4.2.6 2.3 2.5 2.3 4.5c0 3 4.7 8.9 4.7 8.9s4.7-5.9 4.7-8.9C11.7 2.5 9.8.6 7 .6z" fill={C.green} />
              <circle cx="7" cy="4.5" r="1.9" fill={C.bg} />
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: C.text, letterSpacing: -0.2 }}>SpirulinaAI</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, letterSpacing: 0.6 }}>cultivation agent</div>
          </div>
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            style={{
              width: 28, height: 28, borderRadius: 7, background: C.card2,
              border: `1px solid ${C.border}`, color: C.text2, fontSize: 13,
              display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}
          >
            {isDark ? "☀" : "☾"}
          </button>
        </div>

        {/* New conversation */}
        <button
          onClick={onNewChat}
          style={{
            width: "100%", padding: "8px 12px", borderRadius: 8,
            border: `1px solid ${C.border}`, background: C.card,
            color: C.text2, fontSize: 13, display: "flex", alignItems: "center", gap: 8,
            transition: "all .15s", fontWeight: 500,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.green; e.currentTarget.style.color = C.text; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.text2; }}
        >
          <span style={{ fontSize: 17, lineHeight: 1, color: C.green }}>+</span>
          New conversation
        </button>
      </div>

      {/* Conversation list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "6px 8px" }}>
        {isEmpty ? (
          <div style={{ textAlign: "center", padding: "32px 16px", color: C.text3, fontSize: 12, lineHeight: 1.6 }}>
            No conversations yet.
            <br />Start one above.
          </div>
        ) : (
          Object.entries(groups).map(([label, items]) =>
            items.length > 0 ? (
              <div key={label} style={{ marginBottom: 8 }}>
                <div style={{
                  fontSize: 10, fontWeight: 500, letterSpacing: 0.6, color: C.text3,
                  padding: "6px 10px 3px", textTransform: "uppercase", fontFamily: C.mono,
                }}>
                  {label}
                </div>
                {items.map((c) => (
                  <ConvRow key={c.id} conv={c} isActive={c.id === activeConvId}
                    onSelect={onSelectConv} onDelete={onDeleteConv} />
                ))}
              </div>
            ) : null
          )
        )}
      </div>

      {/* Footer: user info + logout */}
      <div style={{
        padding: "10px 12px", borderTop: `1px solid ${C.border}`,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        {/* Avatar */}
        <div style={{
          width: 28, height: 28, borderRadius: 8, flexShrink: 0,
          background: tierBg, border: `1px solid ${tierColor}30`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 700, color: tierColor,
        }}>
          {user?.email?.[0]?.toUpperCase() ?? "?"}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 11.5, color: C.text2, overflow: "hidden",
            whiteSpace: "nowrap", textOverflow: "ellipsis",
          }}>
            {user?.email ?? ""}
          </div>
          <div style={{ fontSize: 10, color: tierColor, fontFamily: C.mono, fontWeight: 600, letterSpacing: 0.3 }}>
            {user?.tier?.toUpperCase() ?? "FREE"}
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={onLogout}
          title="Sign out"
          style={{
            width: 26, height: 26, borderRadius: 6, background: "none",
            border: `1px solid ${C.border}`, color: C.text3, fontSize: 13,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0, cursor: "pointer",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = C.red; e.currentTarget.style.borderColor = `${C.red}60`; e.currentTarget.style.background = C.redSoft; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = C.border; e.currentTarget.style.background = "none"; }}
        >
          ⏻
        </button>
      </div>
    </div>
  );
}
