import {
  sendMessage, listConversations, getConversationMessages, deleteConversation,
  getModelOutputs, getSensorData, connectAlerts,
} from "@/lib/api";

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.resetAllMocks();
});

// ── sendMessage ───────────────────────────────────────────────────────────────

describe("sendMessage", () => {
  it("POSTs to /chat with correct body", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ response: "hello", content: {}, tools_used: [], intent: "KNOWLEDGE", confidence: 0.9 }),
    });

    const result = await sendMessage({ message: "hello", userId: "u1", containerId: "c1", tier: "pro" });

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/chat"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "hello", user_id: "u1", container_id: "c1", tier: "pro", conversation_id: "",
        }),
      })
    );
    expect(result.response).toBe("hello");
  });

  it("throws on non-ok response", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(sendMessage({ message: "x", userId: "u", containerId: "", tier: "free" })).rejects.toThrow(
      "API error 500"
    );
  });
});

// ── listConversations ──────────────────────────────────────────────────────────

describe("listConversations", () => {
  it("returns parsed array on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ id: "c1", title: "pH question" }],
    });

    const conversations = await listConversations("user1");
    expect(conversations).toEqual([{ id: "c1", title: "pH question" }]);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/conversations/user1"), expect.anything());
  });

  it("returns [] when response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false });
    expect(await listConversations("user1")).toEqual([]);
  });

  it("returns [] on network error", async () => {
    global.fetch.mockRejectedValue(new Error("network error"));
    expect(await listConversations("user1")).toEqual([]);
  });
});

// ── getConversationMessages ────────────────────────────────────────────────────

describe("getConversationMessages", () => {
  it("returns parsed messages on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ role: "user", content: "hi" }],
    });

    const messages = await getConversationMessages("user1", "conv1");
    expect(messages).toEqual([{ role: "user", content: "hi" }]);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/conversations/user1/conv1"), expect.anything());
  });

  it("returns [] when response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false });
    expect(await getConversationMessages("user1", "conv1")).toEqual([]);
  });
});

// ── deleteConversation ─────────────────────────────────────────────────────────

describe("deleteConversation", () => {
  it("sends DELETE to /conversations/{userId}/{convId}", async () => {
    global.fetch.mockResolvedValue({ ok: true });
    await deleteConversation("user1", "conv1");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/conversations/user1/conv1"),
      expect.objectContaining({ method: "DELETE" })
    );
  });
});

// ── getModelOutputs ───────────────────────────────────────────────────────────

describe("getModelOutputs", () => {
  it("returns parsed data on success", async () => {
    const mockData = { m1: { anomaly: false, severity: null, rule_findings: [], seasonal: {} } };
    global.fetch.mockResolvedValue({ ok: true, json: async () => mockData });

    const result = await getModelOutputs("container-01");
    expect(result).toEqual(mockData);
  });

  it("returns null when response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false });
    expect(await getModelOutputs("container-01")).toBeNull();
  });

  it("returns null on network error", async () => {
    global.fetch.mockRejectedValue(new Error("timeout"));
    expect(await getModelOutputs("container-01")).toBeNull();
  });
});

// ── getSensorData ─────────────────────────────────────────────────────────────

describe("getSensorData", () => {
  it("returns sensor object on success", async () => {
    const mockSensor = { pH: 9.8, EC: 2100, temperature: 33 };
    global.fetch.mockResolvedValue({ ok: true, json: async () => mockSensor });

    const result = await getSensorData("container-01");
    expect(result).toEqual(mockSensor);
  });

  it("returns null for empty object response", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    expect(await getSensorData("container-01")).toBeNull();
  });

  it("returns null on error", async () => {
    global.fetch.mockRejectedValue(new Error("offline"));
    expect(await getSensorData("container-01")).toBeNull();
  });
});

// ── connectAlerts ─────────────────────────────────────────────────────────────

describe("connectAlerts", () => {
  let mockEventSource;

  beforeEach(() => {
    mockEventSource = { onmessage: null, onerror: null, close: jest.fn() };
    global.EventSource = jest.fn(() => mockEventSource);
  });

  it("opens EventSource with correct URL including containerId", () => {
    connectAlerts("user1", "c1", {});
    expect(EventSource).toHaveBeenCalledWith(expect.stringContaining("/alerts/user1"));
    expect(EventSource).toHaveBeenCalledWith(expect.stringContaining("container_id=c1"));
  });

  it("opens EventSource without container_id param when containerId is empty", () => {
    connectAlerts("user1", "", {});
    expect(EventSource).toHaveBeenCalledWith(expect.not.stringContaining("container_id"));
  });

  it("calls onConnect when type=connected is received", () => {
    const onConnect = jest.fn();
    connectAlerts("user1", "", { onConnect });
    mockEventSource.onmessage({ data: JSON.stringify({ type: "connected" }) });
    expect(onConnect).toHaveBeenCalled();
  });

  it("calls onAlert with text and meta when type=alert is received", () => {
    const onAlert = jest.fn();
    connectAlerts("user1", "", { onAlert });
    mockEventSource.onmessage({
      data: JSON.stringify({ type: "alert", text: "pH dropped!", severity: "critical", affected: ["pH"], source: "model" }),
    });
    expect(onAlert).toHaveBeenCalledWith("pH dropped!", { severity: "critical", affected: ["pH"], source: "model" });
  });

  it("calls onError when EventSource errors", () => {
    const onError = jest.fn();
    connectAlerts("user1", "", { onError });
    mockEventSource.onerror();
    expect(onError).toHaveBeenCalled();
  });

  it("returns a disconnect function that closes the EventSource", () => {
    const disconnect = connectAlerts("user1", "", {});
    disconnect();
    expect(mockEventSource.close).toHaveBeenCalled();
  });

  it("silently ignores malformed SSE frames", () => {
    const onAlert = jest.fn();
    connectAlerts("user1", "", { onAlert });
    expect(() => {
      mockEventSource.onmessage({ data: "not valid json" });
    }).not.toThrow();
    expect(onAlert).not.toHaveBeenCalled();
  });
});
