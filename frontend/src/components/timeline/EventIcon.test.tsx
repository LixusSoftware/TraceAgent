import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EventIcon, getEventColor } from "./EventIcon";

describe("EventIcon", () => {
  it("renders Flag for run.started", () => {
    render(<EventIcon type="run.started" />);
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });
  it("renders fallback for unknown type", () => {
    render(<EventIcon type="unknown.event" />);
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });
});

describe("getEventColor", () => {
  it("returns accent for run.started", () => {
    expect(getEventColor("run.started")).toBe("text-accent");
  });
  it("returns muted for unknown", () => {
    expect(getEventColor("unknown")).toBe("text-muted");
  });
});
