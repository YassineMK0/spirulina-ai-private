import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import AlertsPage from "@/components/alerts/AlertsPage";

const mockAlerts = [
  { id: "1", severity: "critical", affected: ["pH"], source: "model",       text: "pH dropped below 8.5.", time: "10:05", createdAt: "2026-01-01T10:05:00Z" },
  { id: "2", severity: "medium",   affected: ["EC"], source: "rule",        text: "EC is elevated.",       time: "09:30", createdAt: "2026-01-01T09:30:00Z" },
  { id: "3", severity: "low",      affected: ["DO"], source: "rule+model",  text: "DO recovering.",        time: "08:00", createdAt: "2026-01-01T08:00:00Z" },
];

// ── empty state ───────────────────────────────────────────────────────────────

describe("AlertsPage — empty state", () => {
  it("renders 'No alerts yet.' when alerts array is empty", () => {
    render(<AlertsPage alerts={[]} />);
    expect(screen.getByText("No alerts yet.")).toBeInTheDocument();
  });

  it("renders 'No alerts yet.' when alerts prop is omitted", () => {
    render(<AlertsPage />);
    expect(screen.getByText("No alerts yet.")).toBeInTheDocument();
  });
});

// ── alert rendering ───────────────────────────────────────────────────────────

describe("AlertsPage — alert list", () => {
  it("renders all alerts", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("pH dropped below 8.5.")).toBeInTheDocument();
    expect(screen.getByText("EC is elevated.")).toBeInTheDocument();
    expect(screen.getByText("DO recovering.")).toBeInTheDocument();
  });

  it("renders plain-language severity labels, not raw technical words", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByText("Heads Up")).toBeInTheDocument();
    expect(screen.getByText("Good to Know")).toBeInTheDocument();
    // the raw words "CRITICAL"/"MEDIUM"/"LOW" should not leak into the UI
    expect(screen.queryByText(/CRITICAL/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^MEDIUM$/)).not.toBeInTheDocument();
  });

  it("renders affected sensors as friendly names, not raw keys", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("pH Level")).toBeInTheDocument();
    expect(screen.getByText("Nutrient Level")).toBeInTheDocument();
    expect(screen.getByText("Oxygen Level")).toBeInTheDocument();
  });

  it("renders a friendly detection-source label instead of internal system names", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("AI Watch")).toBeInTheDocument();
    expect(screen.getByText("Live Check")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/Threshold Rule/)).not.toBeInTheDocument();
  });

  it("renders timestamps", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText(/10:05/)).toBeInTheDocument();
    expect(screen.getByText(/09:30/)).toBeInTheDocument();
  });
});

// ── message cleanup ──────────────────────────────────────────────────────────

describe("AlertsPage — legacy message cleanup", () => {
  it("strips an old-format technical prefix/suffix from historical alerts", () => {
    const legacy = [{
      id: "9", severity: "critical", affected: ["pH"], source: "rule+model",
      time: "12:00", createdAt: "2026-01-01T12:00:00Z",
      text: "🚨 CRITICAL — container-01: pH of 7.0 is too acidic. Add baking soda.\n\n_Source: Threshold rule + M1 predictor (agreed independently)_",
    }];
    render(<AlertsPage alerts={legacy} />);
    expect(screen.getByText("pH of 7.0 is too acidic. Add baking soda.")).toBeInTheDocument();
    expect(screen.queryByText(/_Source:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/container-01/)).not.toBeInTheDocument();
  });
});

// ── NEW tag ───────────────────────────────────────────────────────────────────

describe("AlertsPage — NEW tag", () => {
  it("marks the most recent alert (by createdAt) as NEW", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });

  it("does not tag older alerts as NEW", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getAllByText("NEW").length).toBe(1);
  });
});

// ── Ask assistant button ─────────────────────────────────────────────────────

describe("AlertsPage — Ask assistant button", () => {
  it("shows the ask-assistant button only for the most recent alert", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    const buttons = screen.getAllByText(/Ask the assistant/);
    expect(buttons.length).toBe(1);
  });

  it("calls onGoChat when the button is clicked", () => {
    const onGoChat = jest.fn();
    render(<AlertsPage alerts={mockAlerts} onGoChat={onGoChat} />);
    fireEvent.click(screen.getByText(/Ask the assistant/));
    expect(onGoChat).toHaveBeenCalledTimes(1);
  });
});

// ── single alert edge case ────────────────────────────────────────────────────

describe("AlertsPage — single alert", () => {
  it("marks the single alert as NEW", () => {
    render(<AlertsPage alerts={[mockAlerts[0]]} />);
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });
});
