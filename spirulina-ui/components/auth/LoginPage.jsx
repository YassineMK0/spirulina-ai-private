"use client";
import { useState } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { authLogin, authSignup } from "@/lib/api";

export default function LoginPage({ onLogin }) {
  const { C } = useTheme();
  const [mode,     setMode]     = useState("login"); // "login" | "signup"
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const fn   = mode === "login" ? authLogin : authSignup;
      const data = await fn(email, password);
      onLogin(data);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh", width: "100%",
      background: C.bg, fontFamily: C.sans,
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 24,
    }}>
      <div style={{ width: "100%", maxWidth: 400 }}>

        {/* Logo */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 40 }}>
          <div style={{
            width: 52, height: 52, borderRadius: 16, marginBottom: 14,
            background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: C.glowSm,
          }}>
            <svg viewBox="0 0 14 14" fill="none" width={28} height={28}>
              <path d="M7 .6C4.2.6 2.3 2.5 2.3 4.5c0 3 4.7 8.9 4.7 8.9s4.7-5.9 4.7-8.9C11.7 2.5 9.8.6 7 .6z" fill={C.green} />
              <circle cx="7" cy="4.5" r="1.9" fill={C.bg} />
            </svg>
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.text, letterSpacing: -0.5 }}>SpirulinaAI</div>
          <div style={{ fontSize: 12, color: C.text3, fontFamily: C.mono, letterSpacing: 0.8, marginTop: 3 }}>
            CULTIVATION AGENT
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: C.card, border: `1px solid ${C.border}`,
          borderRadius: 16, padding: 32,
        }}>
          <h2 style={{ margin: "0 0 6px", fontSize: 17, fontWeight: 600, color: C.text }}>
            {mode === "login" ? "Welcome back" : "Create account"}
          </h2>
          <p style={{ margin: "0 0 24px", fontSize: 13, color: C.text3 }}>
            {mode === "login"
              ? "Sign in to your SpirulinaAI account"
              : "Start managing your spirulina culture with AI"}
          </p>

          <form onSubmit={submit}>
            {/* Email */}
            <label style={{ display: "block", marginBottom: 14 }}>
              <div style={{ fontSize: 11.5, fontWeight: 500, color: C.text2, marginBottom: 6, fontFamily: C.mono, letterSpacing: 0.5 }}>
                EMAIL
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
                style={{
                  width: "100%", boxSizing: "border-box",
                  padding: "10px 14px", borderRadius: 9,
                  background: C.surface, border: `1px solid ${C.border}`,
                  color: C.text, fontSize: 14, fontFamily: C.sans,
                  outline: "none", transition: "border-color .15s",
                }}
                onFocus={(e) => (e.target.style.borderColor = C.green)}
                onBlur={(e)  => (e.target.style.borderColor = C.border)}
              />
            </label>

            {/* Password */}
            <label style={{ display: "block", marginBottom: 20 }}>
              <div style={{ fontSize: 11.5, fontWeight: 500, color: C.text2, marginBottom: 6, fontFamily: C.mono, letterSpacing: 0.5 }}>
                PASSWORD
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder={mode === "signup" ? "At least 6 characters" : "••••••••"}
                style={{
                  width: "100%", boxSizing: "border-box",
                  padding: "10px 14px", borderRadius: 9,
                  background: C.surface, border: `1px solid ${C.border}`,
                  color: C.text, fontSize: 14, fontFamily: C.sans,
                  outline: "none", transition: "border-color .15s",
                }}
                onFocus={(e) => (e.target.style.borderColor = C.green)}
                onBlur={(e)  => (e.target.style.borderColor = C.border)}
              />
            </label>

            {/* Error */}
            {error && (
              <div style={{
                padding: "9px 14px", borderRadius: 8, marginBottom: 16,
                background: C.redSoft, border: `1px solid ${C.red}40`,
                color: C.red, fontSize: 13,
              }}>
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%", padding: "11px 0", borderRadius: 9,
                background: loading ? C.card2 : C.green,
                border: "none", color: loading ? C.text3 : C.bg,
                fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
                fontFamily: C.sans, transition: "all .15s",
              }}
            >
              {loading
                ? (mode === "login" ? "Signing in…" : "Creating account…")
                : (mode === "login" ? "Sign in" : "Create account")}
            </button>
          </form>

          {/* Toggle */}
          <div style={{ marginTop: 20, textAlign: "center", fontSize: 13, color: C.text3 }}>
            {mode === "login" ? "Don't have an account?" : "Already have an account?"}
            {" "}
            <button
              onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}
              style={{
                background: "none", border: "none",
                color: C.green, fontSize: 13, fontWeight: 600,
                cursor: "pointer", padding: 0, fontFamily: C.sans,
              }}
            >
              {mode === "login" ? "Sign up" : "Sign in"}
            </button>
          </div>
        </div>

        {/* Free tier note */}
        <div style={{ marginTop: 20, textAlign: "center", fontSize: 12, color: C.text3 }}>
          Free accounts include <strong style={{ color: C.text2 }}>3 messages</strong> to try the RAG assistant.
          <br />Pro accounts get unlimited access + agent tools + ML dashboard.
        </div>
      </div>
    </div>
  );
}
