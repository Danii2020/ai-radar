/**
 * Spec: web-feed-ui
 * Covers: T19 (audit.md Test Coverage) / AD-11 (contract.md) -- tag chips
 * are a deterministic, page-local projection of the cards actually
 * rendered, never a global vocabulary (there is no /tags endpoint).
 */
import { describe, expect, it } from "vitest";
import { MAX_TAG_CHIPS, topTags } from "./tags";
import type { CardOut } from "./types.generated";

function card(tags: string[] | undefined): CardOut {
  return {
    card_id: `card-${Math.random()}`,
    title: "A Card",
    url: "https://example.com/a",
    source: "Source",
    summary: "Summary",
    tags,
    type: "paper",
    relevance: 5,
    published: "2026-08-28",
    takeaways: [],
    created_at: "2026-08-30T21:41:37.034678+00:00",
    updated_at: "2026-08-30T21:41:37.034678+00:00",
  };
}

describe("topTags", () => {
  it("T19: orders by descending frequency", () => {
    const cards = [
      card(["a", "b"]),
      card(["a"]),
      card(["a", "c"]),
      card(["b"]),
    ];
    // a: 3, b: 2, c: 1
    const result = topTags(cards);
    expect(result.slice(0, 3)).toEqual(["a", "b", "c"]);
  });

  it("T19: breaks equal-frequency ties alphabetically", () => {
    const cards = [card(["zebra"]), card(["apple"]), card(["mango"])];
    expect(topTags(cards, 3)).toEqual(["apple", "mango", "zebra"]);
  });

  it(`T19: caps output at MAX_TAG_CHIPS (${MAX_TAG_CHIPS}) with more than 12 distinct tags`, () => {
    expect(MAX_TAG_CHIPS).toBe(12);
    const tagNames = Array.from(
      { length: 20 },
      (_, i) => `tag-${String(i).padStart(2, "0")}`,
    );
    const cards = tagNames.map((tag) => card([tag]));

    const result = topTags(cards);

    expect(result).toHaveLength(MAX_TAG_CHIPS);
  });

  it("T19: cards with tags: undefined contribute nothing and do not throw", () => {
    const cards = [card(undefined), card(["a"]), card(undefined)];

    expect(() => topTags(cards)).not.toThrow();
    expect(topTags(cards)).toEqual(["a"]);
  });

  it("T19: an all-undefined-tags card list returns an empty result without throwing", () => {
    const cards = [card(undefined), card(undefined)];

    expect(() => topTags(cards)).not.toThrow();
    expect(topTags(cards)).toEqual([]);
  });
});
