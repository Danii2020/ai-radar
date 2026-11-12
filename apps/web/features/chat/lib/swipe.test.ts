/**
 * Spec: web-chat-swipe-handle, O2 (AC3, AC4, AC5). The pure gesture rule: 40 px of horizontal travel
 * and |dx| >= 2 * |dy|. Interface the tests fix: `./swipe` exports `classifySwipe(dx, dy)` returning
 * "left" | "right" | "none" (dx positive = rightward).
 */
import { describe, expect, it } from "vitest";
import { classifySwipe } from "./swipe";

describe("classifySwipe", () => {
  it.each([
    [-60, 8, "left"],
    [-40, 20, "left"], // both boundaries are inclusive
    [-40, 0, "left"],
    [60, 0, "right"],
    [80, 10, "right"],
    [40, -20, "right"],
    [-39, 0, "none"], // too short
    [39, 0, "none"],
    [-60, 31, "none"], // ratio: 60 < 2 * 31
    [-20, -200, "none"], // mostly vertical
    [10, 120, "none"],
    [0, 0, "none"], // a tap
  ])("(%i, %i) -> %s", (dx, dy, expected) => {
    expect(classifySwipe(dx, dy)).toBe(expected);
  });
});
