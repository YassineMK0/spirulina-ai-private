const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Token helpers ─────────────────────────────────────────────────────────────

function getToken() {
  if (typeof window !== "undefined") return localStorage.getItem("spirulina-token") || "";
  return "";
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function authSignup(email, password) {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data; // { token, user: { id, email, tier } }
}

export async function authLogin(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data; // { token, user: { id, email, tier } }
}

export async function authMe() {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json(); // { id, email, tier }
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export async function adminListUsers() {
  try {
    const res = await fetch(`${API_BASE}/admin/users`, { headers: authHeaders() });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

export async function adminDeleteUser(userId) {
  await fetch(`${API_BASE}/admin/users/${userId}`, {
    method:  "DELETE",
    headers: authHeaders(),
  });
}

export async function adminCreateUser(email, password, tier) {
  const res = await fetch(`${API_BASE}/admin/users`, {
    method:  "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password, tier }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data;
}

export async function adminUpdateTier(userId, tier) {
  await fetch(`${API_BASE}/admin/users/${userId}/tier`, {
    method:  "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body:    JSON.stringify({ tier }),
  });
}

export async function adminResetPassword(userId, password) {
  const res = await fetch(`${API_BASE}/admin/users/${userId}/password`, {
    method:  "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body:    JSON.stringify({ password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data;
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export async function sendMessage({ message, userId, containerId, tier, conversationId = "" }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method:  "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body:    JSON.stringify({
      message,
      user_id:         userId,
      container_id:    containerId,
      tier,
      conversation_id: conversationId,
    }),
  });
  if (res.status === 429) {
    const data = await res.json().catch(() => ({}));
    const err  = new Error(data.detail || "Message limit reached");
    err.status = 429;
    throw err;
  }
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
  // { response, content, tools_used, intent, confidence, plan, tool_calls, conversation_id }
}

// ── Conversations ─────────────────────────────────────────────────────────────

export async function listConversations(userId) {
  try {
    const res = await fetch(`${API_BASE}/conversations/${userId}`, { headers: authHeaders() });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

export async function createConversation(userId, title = "New conversation") {
  const res = await fetch(`${API_BASE}/conversations/${userId}`, {
    method:  "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body:    JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json(); // { id, title }
}

export async function getConversationMessages(userId, convId) {
  try {
    const res = await fetch(`${API_BASE}/conversations/${userId}/${convId}`, { headers: authHeaders() });
    if (!res.ok) return [];
    return res.json(); // [{ role, content }]
  } catch { return []; }
}

export async function deleteConversation(userId, convId) {
  await fetch(`${API_BASE}/conversations/${userId}/${convId}`, {
    method:  "DELETE",
    headers: authHeaders(),
  });
}

export async function renameConversation(userId, convId, title) {
  await fetch(`${API_BASE}/conversations/${userId}/${convId}/title`, {
    method:  "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body:    JSON.stringify({ title }),
  });
}

// ── Sensors / ML ──────────────────────────────────────────────────────────────

export async function getModelOutputs(containerId) {
  try {
    const res = await fetch(`${API_BASE}/models/${containerId}`, { cache: "no-store", headers: authHeaders() });
    if (!res.ok) return null;
    return res.json();
  } catch { return null; }
}

export async function getSensorData(containerId) {
  try {
    const res = await fetch(`${API_BASE}/sensors/${containerId}`, { cache: "no-store", headers: authHeaders() });
    if (!res.ok) return null;
    const data = await res.json();
    return Object.keys(data).length ? data : null;
  } catch { return null; }
}

export async function predictCPC(imageFile) {
  const form = new FormData();
  form.append("file", imageFile);
  const res = await fetch(`${API_BASE}/cpc/predict`, {
    method:  "POST",
    headers: authHeaders(), // no Content-Type — let browser set multipart boundary
    body:    form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data; // { cpc_mgml, unit, in_training_range, training_range }
}

export async function predictSpecies(imageFile) {
  const form = new FormData();
  form.append("file", imageFile);
  const res = await fetch(`${API_BASE}/species/predict`, {
    method:  "POST",
    headers: authHeaders(), // no Content-Type — let browser set multipart boundary
    body:    form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data; // { species, confidence, probabilities, is_target_species, warning }
}

// ── SSE alerts ────────────────────────────────────────────────────────────────

export function connectAlerts(userId, containerId, { onAlert, onConnect, onError } = {}) {
  const token = getToken();
  const url   = `${API_BASE}/alerts/${userId}${containerId ? `?container_id=${encodeURIComponent(containerId)}` : ""}`;
  // EventSource doesn't support custom headers — token sent via query param as fallback
  const src   = new EventSource(token ? `${url}${containerId ? "&" : "?"}token=${token}` : url);

  src.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if      (data.type === "connected") onConnect?.();
      else if (data.type === "alert")     onAlert?.(data.text, {
        severity:  data.severity,
        affected:  data.affected,
        source:    data.source,
        createdAt: data.created_at,
      });
    } catch { /* ignore malformed frames */ }
  };

  src.onerror = () => onError?.();
  return () => src.close();
}

// ── Alert history ─────────────────────────────────────────────────────────────

export async function getAlertHistory(userId, limit = 50) {
  try {
    const res = await fetch(`${API_BASE}/alerts/${userId}/history?limit=${limit}`, {
      cache: "no-store", headers: authHeaders(),
    });
    if (!res.ok) return [];
    return res.json(); // [{ id, user_id, container_id, message, severity, source, affected, created_at }]
  } catch { return []; }
}
