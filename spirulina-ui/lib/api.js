const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function sendMessage({ message, userId, containerId, tier }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      user_id:      userId,
      container_id: containerId,
      tier,
    }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json(); // { response, content, tools_used, intent, confidence }
}

export async function getHistory(userId) {
  try {
    const res = await fetch(`${API_BASE}/history/${userId}`);
    if (!res.ok) return [];
    return res.json(); // [{ role, content }]
  } catch {
    return [];
  }
}

export async function clearHistory(userId) {
  await fetch(`${API_BASE}/history/${userId}`, { method: "DELETE" });
}

export async function getModelOutputs(containerId) {
  try {
    const res = await fetch(`${API_BASE}/models/${containerId}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getSensorData(containerId) {
  try {
    const res = await fetch(`${API_BASE}/sensors/${containerId}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    return Object.keys(data).length ? data : null;
  } catch {
    return null;
  }
}

export function connectAlerts(userId, containerId, { onAlert, onConnect, onError } = {}) {
  const url = containerId
    ? `${API_BASE}/alerts/${userId}?container_id=${encodeURIComponent(containerId)}`
    : `${API_BASE}/alerts/${userId}`;
  const es = new EventSource(url);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === "connected") onConnect?.();
      else if (data.type === "alert") onAlert?.(data.text);
    } catch {
      // ignore malformed frames
    }
  };

  es.onerror = () => onError?.();

  return () => es.close();
}
