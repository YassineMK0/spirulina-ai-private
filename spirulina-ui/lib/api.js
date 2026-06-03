const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Chat ─────────────────────────────────────────────────────────────────────

export async function sendMessage({ message, userId, containerId, tier, conversationId = "" }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      message,
      user_id:         userId,
      container_id:    containerId,
      tier,
      conversation_id: conversationId,
    }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
  // { response, content, tools_used, intent, confidence, plan, tool_calls, conversation_id }
}

// ── Conversations ─────────────────────────────────────────────────────────────

export async function listConversations(userId) {
  try {
    const res = await fetch(`${API_BASE}/conversations/${userId}`);
    if (!res.ok) return [];
    return res.json();
    // [{ id, title, created_at, updated_at, message_count }]
  } catch {
    return [];
  }
}

export async function createConversation(userId, title = "New conversation") {
  const res = await fetch(`${API_BASE}/conversations/${userId}`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json(); // { id, title }
}

export async function getConversationMessages(userId, convId) {
  try {
    const res = await fetch(`${API_BASE}/conversations/${userId}/${convId}`);
    if (!res.ok) return [];
    return res.json(); // [{ role, content }]
  } catch {
    return [];
  }
}

export async function deleteConversation(userId, convId) {
  await fetch(`${API_BASE}/conversations/${userId}/${convId}`, { method: "DELETE" });
}

export async function renameConversation(userId, convId, title) {
  await fetch(`${API_BASE}/conversations/${userId}/${convId}/title`, {
    method:  "PATCH",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ title }),
  });
}

// ── Sensors / ML ──────────────────────────────────────────────────────────────

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

// ── SSE alerts ────────────────────────────────────────────────────────────────

export function connectAlerts(userId, containerId, { onAlert, onConnect, onError } = {}) {
  const url = containerId
    ? `${API_BASE}/alerts/${userId}?container_id=${encodeURIComponent(containerId)}`
    : `${API_BASE}/alerts/${userId}`;
  const es = new EventSource(url);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if      (data.type === "connected") onConnect?.();
      else if (data.type === "alert")     onAlert?.(data.text);
    } catch { /* ignore malformed frames */ }
  };

  es.onerror = () => onError?.();
  return () => es.close();
}
