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

  it("renders the alert header label", () => {
    render(<Bubble msg={alertMsg} />);
    expect(screen.getByText(/Anomaly Alert/i)).toBeInTheDocument();
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
    // alert sensor renders "EC ↑"; non-alert sensor renders "pH" with no suffix
    expect(screen.getByText("EC ↑")).toBeInTheDocument();
    expect(screen.getByText("pH")).toBeInTheDocument();
  });

  it("renders the recommended action", () => {
    render(<Bubble msg={diagMsg} />);
    expect(screen.getByText(/recommended action/i)).toBeInTheDocument();
    expect(screen.getByText("Dilute culture to reduce EC.")).toBeInTheDocument();
  });
});

// ── unknown role ──────────────────────────────────────────────────────────────

describe("Bubble — unknown role", () => {
  it("renders nothing for unknown roles", () => {
    const { container } = render(<Bubble msg={{ role: "system", text: "test" }} />);
    expect(container.firstChild).toBeNull();
  });
});
