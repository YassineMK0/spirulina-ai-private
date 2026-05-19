import { sendMessage, getHistory, clearHistory, getModelOutputs, getSensorData, connectAlerts } from "@/lib/api";

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
        body: JSON.stringify({ message: "hello", user_id: "u1", container_id: "c1", tier: "pro" }),
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

// ── getHistory ────────────────────────────────────────────────────────────────

describe("getHistory", () => {
  it("returns parsed array on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ role: "user", content: "hi" }],
    });

    const history = await getHistory("user1");
    expect(history).toEqual([{ role: "user", content: "hi" }]);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/history/user1"));
  });

  it("returns [] when response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false });
    const history = await getHistory("user1");
    expect(history).toEqual([]);
  });

  it("returns [] on network error", async () => {
    global.fetch.mockRejectedValue(new Error("network error"));
    const history = await getHistory("user1");
    expect(history).toEqual([]);
  });
});

// ── clearHistory ──────────────────────────────────────────────────────────────

describe("clearHistory", () => {
  it("sends DELETE to /history/{userId}", async () => {
    global.fetch.mockResolvedValue({ ok: true });
    await clearHistory("user1");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/history/user1"),
      { method: "DELETE" }
    );
  });
});

// ── getModelOutputs ───────────────────────────────────────────────────────────

describe("getModelOutputs", () => {
  it("returns parsed data on success", async () => {
    const mockData = { m1: { anomaly: false }, m2: { prediction: 120 }, m3: { harvest_pct: 20 } };
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

  it("calls onAlert with text when type=alert is received", () => {
    const onAlert = jest.fn();
    connectAlerts("user1", "", { onAlert });
    mockEventSource.onmessage({ data: JSON.stringify({ type: "alert", text: "pH dropped!" }) });
    expect(onAlert).toHaveBeenCalledWith("pH dropped!");
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
