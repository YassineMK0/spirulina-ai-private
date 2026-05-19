import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import Bubble from "@/components/chat/Bubble";

// ── alert role ─────────────────────────────────────────────────────────────────

describe("Bubble — alert role", () => {
  const alertMsg = { role: "alert", text: "pH dropped to 8.1!", time: "14:02" };

  it("renders the alert text", () => {
    render(<Bubble msg={alertMsg} />);
    expect(screen.getByText("pH dropped to 8.1!")).toBeInTheDocument();
  });

  it("renders the SSE label", () => {
    render(<Bubble msg={alertMsg} />);
    expect(screen.getByText(/SSE ALERT/)).toBeInTheDocument();
  });

  it("renders the timestamp", () => {
    render(<Bubble msg={alertMsg} />);
    expect(screen.getByText("14:02")).toBeInTheDocument();
  });
});

// ── user role ──────────────────────────────────────────────────────────────────

describe("Bubble — user role", () => {
  const userMsg = { role: "user", text: "What is the optimal pH?", time: "09:15" };

  it("renders the user message text", () => {
    render(<Bubble msg={userMsg} />);
    expect(screen.getByText("What is the optimal pH?")).toBeInTheDocument();
  });

  it("renders the timestamp", () => {
    render(<Bubble msg={userMsg} />);
    expect(screen.getByText("09:15")).toBeInTheDocument();
  });
});

// ── agent role — text content ─────────────────────────────────────────────────

describe("Bubble — agent role (text)", () => {
  const agentMsg = {
    role: "agent",
    text: "The optimal pH is 9.5–10.5.",
    content: { type: "text", text: "The optimal pH is 9.5–10.5." },
    tools: [],
    time: "09:16",
  };

  it("renders the agent response text", () => {
    render(<Bubble msg={agentMsg} />);
    expect(screen.getByText("The optimal pH is 9.5–10.5.")).toBeInTheDocument();
  });

  it("renders the AgentAvatar (SVG)", () => {
    const { container } = render(<Bubble msg={agentMsg} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

// ── agent role — tool pills ───────────────────────────────────────────────────

describe("Bubble — agent role (with tools)", () => {
  const agentMsg = {
    role: "agent",
    text: "Sensor data retrieved.",
    content: { type: "text", text: "Sensor data retrieved." },
    tools: ["RAG retrieval", "sensor read"],
    time: "09:17",
  };

  it("renders tool pill names", () => {
    render(<Bubble msg={agentMsg} />);
    expect(screen.getByText(/RAG retrieval/)).toBeInTheDocument();
    expect(screen.getByText(/sensor read/)).toBeInTheDocument();
  });
});

// ── agent role — diagnosis content ───────────────────────────────────────────

describe("Bubble — agent role (diagnosis)", () => {
  const diagMsg = {
    role: "agent",
    content: {
      type: "diagnosis",
      cause: "EC too high, turbidity dropping",
      sensors: [
        { label: "EC", val: "3500", unit: "µS/cm", opt: "1500–3000", isAlert: true },
        { label: "pH", val: "9.8", unit: "", opt: "9.5–10.5", isAlert: false },
      ],
      action: { dose: "500mL fresh water", note: "Dilute culture to reduce EC." },
    },
    tools: [],
    time: "10:00",
  };

  it("renders root cause text", () => {
    render(<Bubble msg={diagMsg} />);
    expect(screen.getByText(/EC too high/)).toBeInTheDocument();
  });

  it("renders sensor labels", () => {
    render(<Bubble msg={diagMsg} />);
    // alert sensor renders "EC ▲"; non-alert sensor renders "pH" with no suffix
    expect(screen.getByText("EC ▲")).toBeInTheDocument();
    expect(screen.getByText("pH")).toBeInTheDocument();
  });

  it("renders the recommended action", () => {
    render(<Bubble msg={diagMsg} />);
    expect(screen.getByText(/RECOMMENDED ACTION/)).toBeInTheDocument();
    expect(screen.getByText("500mL fresh water")).toBeInTheDocument();
  });
});

// ── agent role — harvest content ──────────────────────────────────────────────

describe("Bubble — agent role (harvest)", () => {
  const harvestMsg = {
    role: "agent",
    content: {
      type: "harvest",
      body: "Culture is in plateau phase. Harvest window is open.",
      schedule: {
        today:     { label: "moderate", harvest_pct: 20, confidence: 0.78 },
        tomorrow:  { label: "heavy",    harvest_pct: 35, confidence: 0.85 },
        day_after: { label: "heavy",    harvest_pct: 30, confidence: 0.80 },
      },
      recommendation: "Wait until tomorrow — harvest 35% instead of 20% today.",
      turbidity_forecast: { low: 180, prediction: 210, high: 240 },
    },
    tools: ["ML models"],
    time: "11:00",
  };

  it("renders the best day recommendation header", () => {
    render(<Bubble msg={harvestMsg} />);
    // "Wait — harvest tomorrow" appears in the header; multiple elements contain
    // "tomorrow" so we target the specific header text
    expect(screen.getByText("Wait — harvest tomorrow")).toBeInTheDocument();
  });

  it("renders the 3-day harvest percentages", () => {
    render(<Bubble msg={harvestMsg} />);
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("35%")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
  });

  it("renders the M3 recommendation text", () => {
    render(<Bubble msg={harvestMsg} />);
    expect(screen.getByText(/Wait until tomorrow/)).toBeInTheDocument();
  });

  it("renders turbidity forecast section", () => {
    render(<Bubble msg={harvestMsg} />);
    expect(screen.getByText(/M2 TURBIDITY FORECAST/)).toBeInTheDocument();
  });

  it("renders 'Culture not ready' when harvest_pct is 0 for all days", () => {
    const notReadyMsg = {
      role: "agent",
      content: {
        type: "harvest",
        body: "Culture is still growing.",
        schedule: {
          today:     { label: "not_ready", harvest_pct: 0, confidence: 0 },
          tomorrow:  { label: "not_ready", harvest_pct: 0, confidence: 0 },
          day_after: { label: "not_ready", harvest_pct: 0, confidence: 0 },
        },
      },
      tools: [],
      time: "12:00",
    };
    render(<Bubble msg={notReadyMsg} />);
    expect(screen.getByText(/not ready for harvest/i)).toBeInTheDocument();
  });
});

// ── unknown role ──────────────────────────────────────────────────────────────

describe("Bubble — unknown role", () => {
  it("renders nothing for unknown roles", () => {
    const { container } = render(<Bubble msg={{ role: "system", text: "test" }} />);
    expect(container.firstChild).toBeNull();
  });
});
