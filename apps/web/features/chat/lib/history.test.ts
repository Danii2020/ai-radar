/**
 * Spec: web-chat-ui, O1 (AC3, AC4). The history rules the route applies before it calls the
 * backend: the shape check (alternating roles, starts with user, ends with assistant) and the
 * trim (last 20 items, each cut to 4000 characters).
 *
 * Interface the tests fix: `isValidHistory(value: unknown): boolean` and
 * `trimHistory(history: HistoryItem[]): HistoryItem[]`, both from `./history`.
 */
import { describe, expect, it } from "vitest";
import { isValidHistory, trimHistory } from "./history";

type Item = { role: "user" | "assistant"; text: string };

function turns(count: number, firstIndex = 1): Item[] {
  const items: Item[] = [];
  for (let i = firstIndex; i < firstIndex + count; i++) {
    items.push({ role: "user", text: `question ${i}` });
    items.push({ role: "assistant", text: `answer ${i}` });
  }
  return items;
}

describe("isValidHistory", () => {
  it("accepts an empty history and well-formed alternating turns", () => {
    expect(isValidHistory([])).toBe(true);
    expect(isValidHistory(turns(1))).toBe(true);
    expect(isValidHistory(turns(12))).toBe(true);
  });

  it.each([
    ["not an array", "hello"],
    ["null", null],
    ["an object", { role: "user", text: "x" }],
    ["starts with assistant", [{ role: "assistant", text: "a" }, { role: "user", text: "q" }]],
    ["does not alternate", [
      { role: "user", text: "q1" }, { role: "user", text: "q2" },
      { role: "assistant", text: "a" }, { role: "assistant", text: "b" },
    ]],
    ["odd length, ends with user", [...turns(1), { role: "user", text: "dangling" }]],
    ["unknown role", [{ role: "system", text: "q" }, { role: "assistant", text: "a" }]],
    ["missing text", [{ role: "user" }, { role: "assistant", text: "a" }]],
    ["non-string text", [{ role: "user", text: 5 }, { role: "assistant", text: "a" }]],
    ["an item that is not an object", ["q", "a"]],
  ])("rejects %s", (_name, value) => {
    expect(isValidHistory(value)).toBe(false);
  });
});

describe("trimHistory", () => {
  it("keeps a history of 20 items or fewer unchanged", () => {
    expect(trimHistory(turns(10))).toEqual(turns(10));
    expect(trimHistory([])).toEqual([]);
  });

  it("12 completed turns -> only turns 3 to 12 remain, still starting with user", () => {
    const trimmed = trimHistory(turns(12));
    expect(trimmed).toEqual(turns(10, 3));
    expect(trimmed[0].role).toBe("user");
    expect(trimmed[trimmed.length - 1].role).toBe("assistant");
  });

  it("cuts an item longer than 4000 characters to exactly 4000 and leaves shorter ones alone", () => {
    const history: Item[] = [
      { role: "user", text: "u".repeat(4001) },
      { role: "assistant", text: "a".repeat(4000) },
      { role: "user", text: "short" },
      { role: "assistant", text: "x".repeat(9000) },
    ];
    const trimmed = trimHistory(history);
    expect(trimmed.map((item) => item.text.length)).toEqual([4000, 4000, 5, 4000]);
    expect(trimmed.map((item) => item.role)).toEqual(["user", "assistant", "user", "assistant"]);
  });

  it("does not mutate its input", () => {
    const history = turns(12);
    const copy = structuredClone(history);
    trimHistory(history);
    expect(history).toEqual(copy);
  });
});
