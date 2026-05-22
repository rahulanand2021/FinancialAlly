import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import Sparkline from "./Sparkline";

describe("Sparkline", () => {
  it("renders an empty svg when fewer than two points", () => {
    const { container } = render(<Sparkline points={[]} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(container.querySelector("path")).toBeNull();
  });

  it("renders a path for two or more points", () => {
    const { container } = render(
      <Sparkline
        points={[
          { price: 1, timestamp: "t1" },
          { price: 2, timestamp: "t2" },
          { price: 3, timestamp: "t3" },
        ]}
      />,
    );
    const path = container.querySelector("path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("d")?.startsWith("M")).toBe(true);
  });

  it("colors the line green when trending up", () => {
    const { container } = render(
      <Sparkline
        points={[
          { price: 1, timestamp: "t1" },
          { price: 2, timestamp: "t2" },
        ]}
      />,
    );
    expect(container.querySelector("path")?.getAttribute("stroke")).toBe("#16c784");
  });

  it("colors the line red when trending down", () => {
    const { container } = render(
      <Sparkline
        points={[
          { price: 2, timestamp: "t1" },
          { price: 1, timestamp: "t2" },
        ]}
      />,
    );
    expect(container.querySelector("path")?.getAttribute("stroke")).toBe("#ea3943");
  });
});
