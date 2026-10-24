/**
 * Spec: web-chat-ui, O6 (AC8). The WEB-9 rule itself: chat styling uses design tokens only. No
 * hand-authored colour, and every padding, margin, gap and border-radius value is a
 * `var(--...)` (a bare 0 is allowed: it is not a design value).
 *
 * `chat.module.css` is read from disk, so this is red until the file exists.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const CSS_PATH = join(dirname(fileURLToPath(import.meta.url)), "chat.module.css");

const SPACING_PROP =
  /^(?:padding|margin|gap|row-gap|column-gap)(?:-[a-z-]+)?$|^border(?:-[a-z]+)*-radius$/;

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function colourViolations(css: string): string[] {
  return stripComments(css).match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g) ?? [];
}

function spacingViolations(css: string): string[] {
  const violations: string[] = [];
  const declaration = /([a-z-]+)\s*:\s*([^;{}]+)/g;
  let match: RegExpExecArray | null;
  while ((match = declaration.exec(stripComments(css))) !== null) {
    const [, property, value] = match;
    if (!SPACING_PROP.test(property)) continue;
    // `env(safe-area-inset-*)` is a device inset, not a design value, and `max(`/`calc(` are only
    // punctuation around tokens (web-chat-ui-polish, plan Decision 9). Any literal left over still fails.
    const leftover = value
      .replace(/env\(safe-area-inset-(?:top|right|bottom|left)\)/g, "")
      .replace(/var\(--[a-z0-9-]+\)/g, "")
      .replace(/\b(?:max|min|calc)\(|[(),]/g, " ")
      .trim();
    const tokens = leftover === "" ? [] : leftover.split(/\s+/);
    if (tokens.some((token) => token !== "0")) violations.push(`${property}: ${value.trim()}`);
  }
  return violations;
}

describe("chat.module.css uses tokens only", () => {
  const css = readFileSync(CSS_PATH, "utf-8");

  it("has no #hex, rgb(), rgba(), hsl() or hsla() colour", () => {
    expect(colourViolations(css)).toEqual([]);
  });

  it("sets every padding, margin, gap and border-radius from a design token", () => {
    expect(spacingViolations(css)).toEqual([]);
  });

  it("actually styles with tokens (not an empty or token-free file)", () => {
    expect(css).toMatch(/var\(--surface-card\)/);
    expect(css).toMatch(/var\(--space-\d\)/);
  });

  it("follows the OS theme through the tokens: no theme toggle attribute", () => {
    expect(css).not.toMatch(/data-theme/);
  });
});

describe("the checkers fire on violations", () => {
  it("flags a hand-authored colour and a hand-authored spacing value", () => {
    expect(colourViolations(".a { color: #fff; background: rgb(0 0 0); }")).toHaveLength(2);
    expect(spacingViolations(".a { padding: 12px var(--space-2); border-radius: 6px; margin: 0; gap: var(--space-1); }")).toEqual([
      "padding: 12px var(--space-2)",
      "border-radius: 6px",
    ]);
  });

  it("accepts a safe-area inset around tokens but still flags a literal beside it", () => {
    expect(spacingViolations(".a { padding-bottom: max(var(--space-3), env(safe-area-inset-bottom)); }")).toEqual([]);
    expect(spacingViolations(".a { padding-bottom: max(12px, env(safe-area-inset-bottom)); }")).toEqual([
      "padding-bottom: max(12px, env(safe-area-inset-bottom))",
    ]);
  });
});
