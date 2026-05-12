"use client";
import { useState } from "react";
import { C } from "@/lib/theme";
import FreeTier from "@/components/FreeTier";
import ProShell from "@/components/ProShell";

export default function SpirulinaApp() {
  const [tier, setTier] = useState("free");

  // In production these would come from auth/session
  const userId      = "demo-user";
  const containerId = "container-01";

  return (
    <div style={{ width: "100%", minHeight: "100vh", background: C.bg, fontFamily: C.sans, display: "flex", flexDirection: "column", alignItems: "center", padding: "20px 12px" }}>
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 14 }}>
        <div style={{ fontFamily: C.serif, fontSize: 28, fontStyle: "italic", color: "#D4EAD8", letterSpacing: -0.5 }}>SpirulinaAI</div>
        <div style={{ fontSize: 10, color: C.text3, fontFamily: C.mono, letterSpacing: 1.5, marginTop: 3 }}>AUTONOMOUS CULTIVATION INTELLIGENCE</div>
      </div>

      {/* Tier toggle */}
      <div style={{ display: "flex", background: "#080C09", border: `1px solid ${C.border}`, borderRadius: 99, padding: 3, marginBottom: 14, gap: 2 }}>
        {[
          { k: "free", label: "Free · RAG only"            },
          { k: "pro",  label: "Pro · Agent + 3 ML Models"  },
        ].map((b) => (
          <button
            key={b.k}
            onClick={() => setTier(b.k)}
            style={{
              padding: "7px 20px", borderRadius: 99, border: "none", fontFamily: C.sans, fontSize: 12, fontWeight: 700, transition: "all .2s",
              background: tier === b.k ? (b.k === "pro" ? `linear-gradient(135deg,#163A20,${C.green})` : "#2D5A3A") : "transparent",
              color: tier === b.k ? "#fff" : C.text3,
            }}
          >
            {b.label}
          </button>
        ))}
      </div>

      {/* App frame */}
      <div style={{
        width: "100%", maxWidth: tier === "pro" ? 920 : 440, height: 740,
        borderRadius: 18, overflow: "hidden",
        border: `1.5px solid ${tier === "pro" ? C.border2 : "#C9C3B0"}`,
        boxShadow: `0 28px 80px rgba(0,0,0,0.7)${tier === "pro" ? `,0 0 60px ${C.greenGlow}` : ""}`,
        transition: "all .4s ease", display: "flex",
      }}>
        {tier === "pro"
          ? <ProShell userId={userId} containerId={containerId} />
          : <FreeTier onUpgrade={() => setTier("pro")} />
        }
      </div>
    </div>
  );
}
