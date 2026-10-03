/**
 * Spec: feed-structure-refactor
 * Covers: AC4 -- parseFeedSearchParams applies exactly the rules app/page.tsx
 * applied inline before the refactor.
 */
import { describe, expect, it } from "vitest";
import { parseFeedSearchParams } from "./search-params";

describe("parseFeedSearchParams", () => {
  it("returns the tag unchanged -- not trimmed -- when it has a non-whitespace character", () => {
    expect(parseFeedSearchParams({ tag: " agents " })).toEqual({
      tag: " agents ",
      cursor: undefined,
    });
  });

  it.each([
    ["absent", {}],
    ["an array", { tag: ["a", "b"] }],
    ["an empty string", { tag: "" }],
    ["whitespace only", { tag: "   " }],
    ["whitespace of mixed kinds", { tag: " \t\n " }],
    ["explicitly undefined", { tag: undefined }],
  ])("tag is undefined when it is %s", (_label, params) => {
    expect(parseFeedSearchParams(params).tag).toBeUndefined();
  });

  it("returns the cursor byte-identical, special characters included", () => {
    expect(parseFeedSearchParams({ cursor: "a+b/c=" }).cursor).toBe("a+b/c=");
    expect(parseFeedSearchParams({ cursor: " padded " }).cursor).toBe(" padded ");
  });

  it.each([
    ["absent", {}],
    ["an array", { cursor: ["x", "y"] }],
    ["an empty string", { cursor: "" }],
  ])("cursor is undefined when it is %s", (_label, params) => {
    expect(parseFeedSearchParams(params).cursor).toBeUndefined();
  });

  it("parses tag and cursor independently of each other", () => {
    expect(parseFeedSearchParams({ tag: "   ", cursor: "a+b/c=" })).toEqual({
      tag: undefined,
      cursor: "a+b/c=",
    });
    expect(parseFeedSearchParams({ tag: ["a", "b"] })).toEqual({
      tag: undefined,
      cursor: undefined,
    });
    expect(parseFeedSearchParams({ cursor: "" })).toEqual({
      tag: undefined,
      cursor: undefined,
    });
    expect(parseFeedSearchParams({ tag: "agents", cursor: "abc" })).toEqual({
      tag: "agents",
      cursor: "abc",
    });
  });

  it("ignores unrelated search params", () => {
    expect(parseFeedSearchParams({ utm_source: "x", tag: "llm" })).toEqual({
      tag: "llm",
      cursor: undefined,
    });
  });
});
