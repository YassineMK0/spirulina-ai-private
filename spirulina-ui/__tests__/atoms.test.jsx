import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { Dot, Tag, Label, AgentAvatar, ToolPills, SpinnerDots } from "@/components/atoms";

describe("Dot", () => {
  it("renders a div", () => {
    const { container } = render(<Dot />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("applies blink animation when blink=true", () => {
    const { container } = render(<Dot blink />);
    expect(container.firstChild.style.animation).toMatch(/blink/);
  });

  it("has no animation when blink=false (default)", () => {
    const { container } = render(<Dot />);
    expect(container.firstChild.style.animation).toBeFalsy();
  });

  it("uses custom size", () => {
    const { container } = render(<Dot size={12} />);
    expect(container.firstChild.style.width).toBe("12px");
    expect(container.firstChild.style.height).toBe("12px");
  });

  it("uses custom color", () => {
    const { container } = render(<Dot color="#FF0000" />);
    expect(container.firstChild.style.background).toBe("rgb(255, 0, 0)");
  });
});

describe("Tag", () => {
  it("renders children text", () => {
    render(<Tag>ACTIVE</Tag>);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("renders as a span", () => {
    const { container } = render(<Tag>TEST</Tag>);
    expect(container.firstChild.tagName).toBe("SPAN");
  });
});

describe("Label", () => {
  it("renders children text", () => {
    render(<Label>SENSOR DATA</Label>);
    expect(screen.getByText("SENSOR DATA")).toBeInTheDocument();
  });

  it("renders as a div", () => {
    const { container } = render(<Label>SECTION</Label>);
    expect(container.firstChild.tagName).toBe("DIV");
  });
});

describe("AgentAvatar", () => {
  it("renders with default size", () => {
    const { container } = render(<AgentAvatar />);
    expect(container.firstChild.style.width).toBe("26px");
    expect(container.firstChild.style.height).toBe("26px");
  });

  it("renders with custom size", () => {
    const { container } = render(<AgentAvatar size={40} />);
    expect(container.firstChild.style.width).toBe("40px");
    expect(container.firstChild.style.height).toBe("40px");
  });

  it("contains an SVG icon", () => {
    const { container } = render(<AgentAvatar />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

describe("ToolPills", () => {
  it("renders tool names", () => {
    render(<ToolPills tools={["RAG retrieval", "ML models"]} />);
    expect(screen.getByText(/RAG retrieval/)).toBeInTheDocument();
    expect(screen.getByText(/ML models/)).toBeInTheDocument();
  });

  it("returns null when tools is empty", () => {
    const { container } = render(<ToolPills tools={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when tools is undefined", () => {
    const { container } = render(<ToolPills />);
    expect(container.firstChild).toBeNull();
  });

  it("prepends a checkmark to each tool", () => {
    render(<ToolPills tools={["sensor read"]} />);
    expect(screen.getByText(/✓ sensor read/)).toBeInTheDocument();
  });
});

describe("SpinnerDots", () => {
  it("renders three dots", () => {
    const { container } = render(<SpinnerDots />);
    // firstChild = the flex wrapper; its children are the 3 dot divs
    expect(container.firstChild.children.length).toBe(3);
  });

  it("each dot has a blink animation", () => {
    const { container } = render(<SpinnerDots />);
    const dots = Array.from(container.firstChild.children);
    dots.forEach((dot) => {
      expect(dot.style.animation).toMatch(/blink/);
    });
  });
});
