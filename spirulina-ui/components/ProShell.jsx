"use client";
import { useState, useEffect } from "react";
import { C } from "@/lib/theme";
import { Dot } from "@/components/atoms";
import Sidebar from "@/components/Sidebar";
import AgentChat from "@/components/chat/AgentChat";
import DashboardPage from "@/components/dashboard/DashboardPage";
import AlertsPage from "@/components/alerts/AlertsPage";
import ModelsPage from "@/components/models/ModelsPage";
import { connectAlerts, getSensorData } from "@/lib/api";

export default function ProShell({ userId, containerId }) {
  const [page, setPage]             = useState("chat");
  const [alerts, setAlerts]         = useState([]);
  const [chatAlerts, setChatAlerts] = useState([]);  // injected into AgentChat
  const [sensorData, setSensorData] = useState(null);
  const [mlStatus]                   = useState({});

  const now = () => new Date().toTimeString().slice(0, 5);

  // Poll sensor data every 10 s
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const data = await getSensorData(containerId);
      if (!cancelled && data) setSensorData(data);
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [containerId]);

  // SSE alert stream — runs once per session at the ProShell level
  useEffect(() => {
    const disconnect = connectAlerts(userId, containerId, {
      onAlert: (text, meta) => {
        const entry = {
          text, time: now(),
          severity: meta?.severity || "medium",
          affected: meta?.affected || [],
          source:   meta?.source   || "model",
        };
        setAlerts((prev) => [...prev, entry]);
        setChatAlerts((prev) => [...prev, entry]);  // mirrors into chat
      },
    });
    return disconnect;
  }, [userId, containerId]);

  const activeAlerts = alerts.filter((a) => a.severity === "critical" || a.severity === "medium");

  const titles = {
    chat:      "Agent Chat",
    dashboard: "Live Dashboard",
    alerts:    "Alerts",
    models:    "ML Models",
  };

  return (
    <div style={{ display: "flex", height: "100%", width: "100%", background: C.bg }}>
      <Sidebar
        page={page}
        setPage={setPage}
        alertCount={activeAlerts.length}
        mlStatus={mlStatus}
      />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {/* Topbar */}
        <div style={{ padding: "11px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", background: C.surface, flexShrink: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{titles[page]}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 8.5, fontFamily: C.mono, color: C.text3 }}>
              <Dot size={5} blink />MQTT LIVE
            </div>
            {activeAlerts.length > 0 && (
              <div
                onClick={() => setPage("alerts")}
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 20, background: C.redSoft, border: "1px solid #4A1010", fontSize: 8.5, fontWeight: 700, color: C.red, fontFamily: C.mono, cursor: "pointer" }}
              >
                <Dot color={C.red} size={5} blink /> {activeAlerts.length} ACTIVE ALERT{activeAlerts.length > 1 ? "S" : ""}
              </div>
            )}
          </div>
        </div>

        {/* Pages */}
        {page === "chat"      && (
          <AgentChat
            userId={userId}
            containerId={containerId}
            tier="pro"
            incomingAlerts={chatAlerts}
          />
        )}
        {page === "dashboard" && <DashboardPage sensorData={sensorData} />}
        {page === "alerts"    && <AlertsPage alerts={alerts} onGoChat={() => setPage("chat")} />}
        {page === "models"    && <ModelsPage containerId={containerId} />}
      </div>
    </div>
  );
}
