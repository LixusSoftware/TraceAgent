// @vitest-environment node
import { describe, expect, it } from "vitest";
// @ts-expect-error the app's tsconfig has no Node types; vitest runs this file in Node
import { readFileSync } from "node:fs";

const css: string = readFileSync(new URL("../index.css", import.meta.url), "utf8");

// Text on the three surfaces of each theme must stay readable (WCAG AA for normal text: 4.5:1).

function tokens(block: RegExp): Record<string, string> {
  const body = css.match(block)?.[1] ?? "";
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

describe.each([
  ["light theme", tokens(/:root\s*\{([^}]*)\}/)],
  ["dark theme", tokens(/\.dark\s*\{([^}]*)\}/)],
])("%s", (_name, theme) => {
  const backgrounds = ["bg", "surface", "surface-strong"];

  it.each(["text", "muted", "accent", "danger", "warning", "info"])("%s text reads on every surface", (color) => {
    for (const background of backgrounds) {
      expect(contrast(theme[color], theme[background]), `${color} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("text on an accent background reads", () => {
    // Active buttons are painted with the accent color and use the page background color for their text.
    expect(contrast(theme.bg, theme.accent)).toBeGreaterThanOrEqual(4.5);
  });
});
