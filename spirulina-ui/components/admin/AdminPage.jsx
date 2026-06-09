"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useTheme } from "@/lib/ThemeContext";
import {
  adminListUsers, adminCreateUser,
  adminDeleteUser, adminUpdateTier, adminResetPassword,
} from "@/lib/api";

// ── Tier helpers ──────────────────────────────────────────────────────────────
const TIERS = ["free", "pro", "admin"];

function tierColor(tier, C) {
  if (tier === "admin") return { fg: C.teal,  bg: `${C.teal}18`,  border: `${C.teal}30`  };
  if (tier === "pro")   return { fg: C.green, bg: `${C.green}18`, border: `${C.green}30` };
  return                       { fg: C.text3, bg: `${C.text3}12`, border: `${C.border}`   };
}

function TierBadge({ tier, C }) {
  const { fg, bg, border } = tierColor(tier, C);
  return (
    <span style={{
      padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
      fontFamily: C.mono, background: bg, color: fg, border: `1px solid ${border}`,
      letterSpacing: 0.3,
    }}>
      {tier.toUpperCase()}
    </span>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent, C }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 12, padding: "16px 20px", flex: 1,
      borderTop: `2px solid ${accent || C.border}`,
    }}>
      <div style={{ fontSize: 26, fontWeight: 700, color: accent || C.text, fontFamily: C.mono }}>{value}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: C.text2, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: C.text3, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────
function Modal({ title, onClose, children, C }) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      background: "rgba(0,0,0,.6)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}
    onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.card, border: `1px solid ${C.border}`,
          borderRadius: 16, padding: 28, width: 400, maxWidth: "90vw",
          boxShadow: "0 24px 64px rgba(0,0,0,.5)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: C.text }}>{title}</h3>
          <button onClick={onClose} style={{
            width: 26, height: 26, borderRadius: 6, border: `1px solid ${C.border}`,
            background: "none", color: C.text3, fontSize: 16, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children, C }) {
  return (
    <label style={{ display: "block", marginBottom: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: C.text3, fontFamily: C.mono, letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase" }}>{label}</div>
      {children}
    </label>
  );
}

function Input({ value, onChange, type = "text", placeholder, C }) {
  return (
    <input
      type={type} value={value} onChange={onChange} placeholder={placeholder}
      style={{
        width: "100%", boxSizing: "border-box",
        padding: "9px 12px", borderRadius: 8,
        background: C.surface, border: `1px solid ${C.border}`,
        color: C.text, fontSize: 13.5, fontFamily: C.sans, outline: "none",
      }}
      onFocus={(e) => (e.target.style.borderColor = C.green)}
      onBlur={(e)  => (e.target.style.borderColor = C.border)}
    />
  );
}

function Btn({ onClick, children, variant = "default", disabled, C }) {
  const styles = {
    primary: { background: C.green,   color: C.bg,    border: "none" },
    danger:  { background: C.redSoft, color: C.red,   border: `1px solid ${C.red}40` },
    default: { background: C.card2,   color: C.text2, border: `1px solid ${C.border}` },
  };
  const s = styles[variant];
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: "9px 18px", borderRadius: 8, fontSize: 13, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer", fontFamily: C.sans,
      opacity: disabled ? 0.5 : 1, transition: "opacity .15s", ...s,
    }}>
      {children}
    </button>
  );
}

// ── Add User modal ────────────────────────────────────────────────────────────
function AddUserModal({ onClose, onCreated, C }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [tier,     setTier]     = useState("free");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async () => {
    setLoading(true); setError("");
    try {
      await adminCreateUser(email, password, tier);
      onCreated();
      onClose();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <Modal title="Add New User" onClose={onClose} C={C}>
      <Field label="Email" C={C}>
        <Input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="user@example.com" C={C} />
      </Field>
      <Field label="Password" C={C}>
        <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="Min. 6 characters" C={C} />
      </Field>
      <Field label="Tier" C={C}>
        <select value={tier} onChange={(e) => setTier(e.target.value)} style={{
          width: "100%", padding: "9px 12px", borderRadius: 8,
          background: C.surface, border: `1px solid ${C.border}`,
          color: C.text, fontSize: 13.5, fontFamily: C.mono,
        }}>
          {TIERS.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
        </select>
      </Field>
      {error && <div style={{ padding: "8px 12px", borderRadius: 8, background: C.redSoft, color: C.red, fontSize: 12.5, marginBottom: 14 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Btn onClick={onClose} C={C}>Cancel</Btn>
        <Btn onClick={submit} variant="primary" disabled={loading || !email || !password} C={C}>
          {loading ? "Creating…" : "Create User"}
        </Btn>
      </div>
    </Modal>
  );
}

// ── Reset Password modal ──────────────────────────────────────────────────────
function ResetPasswordModal({ user, onClose, onDone, C }) {
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async () => {
    setLoading(true); setError("");
    try {
      await adminResetPassword(user.id, password);
      onDone();
      onClose();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <Modal title={`Reset Password — ${user.email}`} onClose={onClose} C={C}>
      <Field label="New Password" C={C}>
        <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="Min. 6 characters" C={C} />
      </Field>
      {error && <div style={{ padding: "8px 12px", borderRadius: 8, background: C.redSoft, color: C.red, fontSize: 12.5, marginBottom: 14 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Btn onClick={onClose} C={C}>Cancel</Btn>
        <Btn onClick={submit} variant="primary" disabled={loading || password.length < 6} C={C}>
          {loading ? "Resetting…" : "Reset Password"}
        </Btn>
      </div>
    </Modal>
  );
}

// ── User row ──────────────────────────────────────────────────────────────────
function UserRow({ user, onDelete, onTierChange, onResetPassword, currentUserId, C }) {
  const [hover,      setHover]      = useState(false);
  const [confirming, setConfirming] = useState(false);
  const isSelf = user.id === currentUserId;
  const { fg } = tierColor(user.tier, C);

  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setConfirming(false); }}
      style={{ background: hover ? `${C.green}06` : "transparent", transition: "background .12s" }}
    >
      {/* Avatar + Email */}
      <td style={{ padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 9, flexShrink: 0,
            background: `${fg}18`, border: `1px solid ${fg}30`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: fg,
          }}>
            {user.email[0].toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize: 13.5, color: C.text, fontWeight: 500 }}>
              {user.email}
              {isSelf && <span style={{ marginLeft: 6, fontSize: 9.5, color: C.green, fontFamily: C.mono, fontWeight: 700, background: `${C.green}18`, padding: "1px 6px", borderRadius: 4 }}>YOU</span>}
            </div>
            <div style={{ fontSize: 10.5, color: C.text3, fontFamily: C.mono, marginTop: 2 }}>
              {user.id.slice(0, 8)}…
            </div>
          </div>
        </div>
      </td>

      {/* Tier */}
      <td style={{ padding: "12px 16px" }}>
        {isSelf ? <TierBadge tier={user.tier} C={C} /> : (
          <select
            value={user.tier}
            onChange={(e) => onTierChange(user.id, e.target.value)}
            style={{
              padding: "5px 10px", borderRadius: 7, fontSize: 12,
              background: C.card2, border: `1px solid ${C.border}`,
              color: fg, fontFamily: C.mono, fontWeight: 600, cursor: "pointer",
            }}
          >
            {TIERS.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
          </select>
        )}
      </td>

      {/* Messages */}
      <td style={{ padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            fontSize: 13, fontWeight: 600, color: C.text2, fontFamily: C.mono,
          }}>
            {user.message_count ?? 0}
          </div>
          {user.tier === "free" && (
            <div style={{
              fontSize: 10, color: C.text3, background: C.card2,
              padding: "1px 6px", borderRadius: 4, fontFamily: C.mono,
            }}>
              / 3
            </div>
          )}
        </div>
      </td>

      {/* Joined */}
      <td style={{ padding: "12px 16px", fontSize: 12, color: C.text3, fontFamily: C.mono }}>
        {user.created_at ? new Date(user.created_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"}
      </td>

      {/* Actions */}
      <td style={{ padding: "12px 16px" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {/* Reset password */}
          <button
            onClick={() => onResetPassword(user)}
            title="Reset password"
            style={{
              padding: "5px 10px", borderRadius: 6, fontSize: 11.5,
              background: "none", border: `1px solid ${C.border}`,
              color: C.text3, cursor: "pointer", fontFamily: C.sans,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = C.green; e.currentTarget.style.borderColor = `${C.green}50`; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = C.border; }}
          >
            Reset pwd
          </button>

          {/* Delete */}
          {!isSelf && (
            confirming ? (
              <div style={{ display: "flex", gap: 4 }}>
                <button onClick={() => onDelete(user.id)} style={{
                  padding: "5px 10px", borderRadius: 6, fontSize: 11.5, fontWeight: 600,
                  background: C.redSoft, border: `1px solid ${C.red}50`, color: C.red, cursor: "pointer",
                }}>Confirm</button>
                <button onClick={() => setConfirming(false)} style={{
                  padding: "5px 8px", borderRadius: 6, fontSize: 11.5,
                  background: "none", border: `1px solid ${C.border}`, color: C.text3, cursor: "pointer",
                }}>Cancel</button>
              </div>
            ) : (
              <button onClick={() => setConfirming(true)} style={{
                padding: "5px 10px", borderRadius: 6, fontSize: 11.5,
                background: "none", border: `1px solid ${C.border}`,
                color: C.text3, cursor: "pointer", fontFamily: C.sans,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = C.red; e.currentTarget.style.borderColor = `${C.red}60`; e.currentTarget.style.background = C.redSoft; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = C.border; e.currentTarget.style.background = "none"; }}
              >
                Delete
              </button>
            )
          )}
        </div>
      </td>
    </tr>
  );
}

// ── Main admin dashboard ──────────────────────────────────────────────────────
export default function AdminPage({ currentUserId }) {
  const { C } = useTheme();
  const [users,       setUsers]       = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [search,      setSearch]      = useState("");
  const [filterTier,  setFilterTier]  = useState("all");
  const [showAdd,     setShowAdd]     = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [toast,       setToast]       = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setUsers(await adminListUsers());
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 2500); };

  const handleDelete = async (userId) => {
    await adminDeleteUser(userId);
    showToast("User deleted");
    await refresh();
  };

  const handleTierChange = async (userId, tier) => {
    await adminUpdateTier(userId, tier);
    showToast(`Tier updated to ${tier}`);
    await refresh();
  };

  // Stats
  const stats = useMemo(() => ({
    total:    users.length,
    free:     users.filter((u) => u.tier === "free").length,
    pro:      users.filter((u) => u.tier === "pro").length,
    admin:    users.filter((u) => u.tier === "admin").length,
    messages: users.reduce((s, u) => s + (u.message_count || 0), 0),
  }), [users]);

  // Filtered list
  const filtered = useMemo(() => users.filter((u) => {
    const matchSearch = !search || u.email.toLowerCase().includes(search.toLowerCase());
    const matchTier   = filterTier === "all" || u.tier === filterTier;
    return matchSearch && matchTier;
  }), [users, search, filterTier]);

  return (
    <div style={{ padding: "28px 32px", maxWidth: 1100, fontFamily: C.sans }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 200,
          background: C.green, color: C.bg, padding: "10px 18px",
          borderRadius: 10, fontSize: 13, fontWeight: 600,
          boxShadow: C.glowSm, animation: "fadein .2s ease",
        }}>
          {toast}
        </div>
      )}

      {/* Modals */}
      {showAdd && (
        <AddUserModal C={C} onClose={() => setShowAdd(false)} onCreated={() => { refresh(); showToast("User created"); }} />
      )}
      {resetTarget && (
        <ResetPasswordModal C={C} user={resetTarget} onClose={() => setResetTarget(null)} onDone={() => showToast("Password reset")} />
      )}

      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: C.text, letterSpacing: -0.3 }}>Admin Dashboard</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12.5, color: C.text3 }}>Manage users, tiers, and access</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={refresh} style={{
            padding: "8px 14px", borderRadius: 8, fontSize: 12.5,
            background: C.card, border: `1px solid ${C.border}`, color: C.text2, cursor: "pointer",
          }}>
            ↻ Refresh
          </button>
          <button onClick={() => setShowAdd(true)} style={{
            padding: "8px 16px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
            background: C.green, border: "none", color: C.bg, cursor: "pointer",
          }}>
            + Add User
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 28 }}>
        <StatCard label="Total Users"    value={stats.total}    sub="registered accounts"      accent={C.text2}  C={C} />
        <StatCard label="Free"           value={stats.free}     sub="3-message limit"          accent={C.text3}  C={C} />
        <StatCard label="Pro"            value={stats.pro}      sub="unlimited access"         accent={C.green}  C={C} />
        <StatCard label="Admin"          value={stats.admin}    sub="full access"              accent={C.teal}   C={C} />
        <StatCard label="Total Messages" value={stats.messages} sub="across all conversations" accent={C.border} C={C} />
      </div>

      {/* Search + filter toolbar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <div style={{ position: "relative", flex: 1 }}>
          <span style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: C.text3, fontSize: 13 }}>⌕</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by email…"
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "9px 12px 9px 30px", borderRadius: 8,
              background: C.card, border: `1px solid ${C.border}`,
              color: C.text, fontSize: 13, fontFamily: C.sans, outline: "none",
            }}
            onFocus={(e) => (e.target.style.borderColor = C.green)}
            onBlur={(e)  => (e.target.style.borderColor = C.border)}
          />
        </div>
        <div style={{ display: "flex", background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
          {["all", ...TIERS].map((t) => (
            <button key={t} onClick={() => setFilterTier(t)} style={{
              padding: "9px 14px", border: "none", fontSize: 12, fontWeight: 600,
              background: filterTier === t ? C.green : "none",
              color:      filterTier === t ? C.bg    : C.text3,
              cursor: "pointer", fontFamily: C.mono, transition: "all .12s",
              borderRight: `1px solid ${C.border}`,
            }}>
              {t === "all" ? "ALL" : t.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div style={{
        background: C.card, border: `1px solid ${C.border}`,
        borderRadius: 12, overflow: "hidden",
      }}>
        {loading ? (
          <div style={{ padding: 32, textAlign: "center", color: C.text3, fontSize: 13 }}>Loading users…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: C.text3, fontSize: 13 }}>
            {search || filterTier !== "all" ? "No users match the filter." : "No users yet."}
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: C.surface, borderBottom: `1px solid ${C.border}` }}>
                {["User", "Tier", "Messages", "Joined", "Actions"].map((h) => (
                  <th key={h} style={{
                    padding: "10px 16px", textAlign: "left", fontSize: 10.5,
                    fontWeight: 700, color: C.text3, fontFamily: C.mono,
                    letterSpacing: 0.8, textTransform: "uppercase",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <tr key={u.id} style={{ borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none" }}>
                  <UserRow
                    user={u}
                    onDelete={handleDelete}
                    onTierChange={handleTierChange}
                    onResetPassword={setResetTarget}
                    currentUserId={currentUserId}
                    C={C}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer legend */}
      <div style={{ marginTop: 16, display: "flex", gap: 20, flexWrap: "wrap" }}>
        {[
          { tier: "free",  note: "3 message limit — RAG only" },
          { tier: "pro",   note: "Unlimited — agent + ML + IoT" },
          { tier: "admin", note: "Unlimited — full access + this panel" },
        ].map(({ tier, note }) => (
          <div key={tier} style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <TierBadge tier={tier} C={C} />
            <span style={{ fontSize: 11.5, color: C.text3 }}>{note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
