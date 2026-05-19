import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import AlertsPage from "@/components/alerts/AlertsPage";

const mockAlerts = [
  { severity: "critical", score: 0.91, trend: "declining", text: "pH dropped below 8.5.", time: "10:05" },
  { severity: "medium",   score: 0.62, trend: "stable",    text: "EC is elevated.",       time: "09:30" },
  { severity: "low",      score: 0.22, trend: "recovering", text: "DO recovering.",        time: "08:00" },
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

  it("renders severity in title (uppercase)", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText(/CRITICAL/)).toBeInTheDocument();
    expect(screen.getByText(/MEDIUM/)).toBeInTheDocument();
    expect(screen.getByText(/LOW/)).toBeInTheDocument();
  });

  it("renders anomaly score and trend", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText(/Score 0.910/)).toBeInTheDocument();
    expect(screen.getByText(/Trend: declining/)).toBeInTheDocument();
  });

  it("renders timestamps", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    expect(screen.getByText("10:05")).toBeInTheDocument();
    expect(screen.getByText("09:30")).toBeInTheDocument();
  });
});

// ── active / past tags ────────────────────────────────────────────────────────

describe("AlertsPage — ACTIVE / PAST tags", () => {
  it("marks the most recent alert (displayed first) as ACTIVE", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    // alerts are displayed in reverse order — first rendered = last in array = critical (index 0 reversed)
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("renders PAST tags for older alerts", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    const pastTags = screen.getAllByText("PAST");
    expect(pastTags.length).toBe(2);
  });
});

// ── Ask agent button ──────────────────────────────────────────────────────────

describe("AlertsPage — Ask agent button", () => {
  it("shows 'Ask agent' button only for the active alert", () => {
    render(<AlertsPage alerts={mockAlerts} />);
    const buttons = screen.getAllByText(/Ask agent/);
    expect(buttons.length).toBe(1);
  });

  it("calls onGoChat when 'Ask agent' button is clicked", () => {
    const onGoChat = jest.fn();
    render(<AlertsPage alerts={mockAlerts} onGoChat={onGoChat} />);
    fireEvent.click(screen.getByText(/Ask agent/));
    expect(onGoChat).toHaveBeenCalledTimes(1);
  });
});

// ── single alert edge case ────────────────────────────────────────────────────

describe("AlertsPage — single alert", () => {
  it("marks the single alert as ACTIVE (not PAST)", () => {
    render(<AlertsPage alerts={[mockAlerts[0]]} />);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.queryByText("PAST")).not.toBeInTheDocument();
  });
});
