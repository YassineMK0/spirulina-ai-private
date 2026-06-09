"use client";
import { useAuth } from "@/lib/AuthContext";
import { useTheme } from "@/lib/ThemeContext";
import LoginPage from "@/components/auth/LoginPage";
import SpirulinaApp from "@/components/SpirulinaApp";

export default function AppGate() {
  const { user, loading, login } = useAuth();
  const { C } = useTheme();

  if (loading) {
    return (
      <div style={{
        height: "100vh", width: "100%",
        background: C.bg, display: "flex",
        alignItems: "center", justifyContent: "center",
        fontFamily: C.sans,
      }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            animation: "blink 1.6s infinite",
          }}>
            <svg viewBox="0 0 14 14" fill="none" width={20} height={20}>
              <path d="M7 .6C4.2.6 2.3 2.5 2.3 4.5c0 3 4.7 8.9 4.7 8.9s4.7-5.9 4.7-8.9C11.7 2.5 9.8.6 7 .6z" fill={C.bg} />
              <circle cx="7" cy="4.5" r="1.9" fill={C.green} />
            </svg>
          </div>
          <span style={{ fontSize: 12, color: C.text3, fontFamily: C.mono }}>Loading…</span>
        </div>
      </div>
    );
  }

  if (!user) return <LoginPage onLogin={login} />;

  return <SpirulinaApp user={user} />;
}
