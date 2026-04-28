import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LaunchConsole } from "./LaunchConsole";

describe("LaunchConsole", () => {
  it("renders form fields", () => {
    render(<LaunchConsole />);
    expect(screen.getByPlaceholderText("e.g. coding-agent")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Describe the task...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /EXEC/i })).toBeInTheDocument();
  });

  it("toggles system prompt", () => {
    render(<LaunchConsole />);
    const toggle = screen.getByText("System Prompt");
    fireEvent.click(toggle);
    expect(screen.getByPlaceholderText("Optional system prompt...")).toBeInTheDocument();
  });
});
