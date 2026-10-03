/**
 * Spec: web-feed-ui
 * Covers: T14-T17 (audit.md Test Coverage) / Guarantee 6, 7 / AD-6
 * (contract.md) -- the bounded empty-page drain that mitigates `feed-api`'s
 * Guarantee 4 (`FilterExpression` applied after `Limit`).
 *
 * `fetchFeed` (from `./client`) is mocked directly rather than stubbing
 * `globalThis.fetch`, since `load-feed.ts` imports it directly per
 * contract.md's interface for this module.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CardOut } from "./types.generated";

vi.mock("./client", () => ({
  fetchFeed: vi.fn(),
}));

import { fetchFeed } from "./client";
import { MAX_DRAIN_REQUESTS, loadFeed } from "./load-feed";

// The live-verified fixture from contract.md/intent.md: a probed
// ?tag=zzz-no-such-tag&limit=5 response -- an empty page carrying a live
// cursor (Guarantee 4 in the wild).
const LIVE_CURSOR =
  "eyJjYXJkX2lkIjoiOTgzMTAyYjNlYTNiNDM0MCIsImdzaV9wayI6IkNBUkQiLCJnc2lfc2siOiIwMDkjMjAyNi0wOC0yOCJ9";

function fullCard(overrides: Partial<CardOut> = {}): CardOut {
  return {
    card_id: "card-1",
    title: "A Card Title",
    url: "https://example.com/a",
    source: "Simon Willison",
    summary: "A summary.",
    tags: ["llm"],
    type: "paper",
    relevance: 8,
    published: "2026-08-28",
    takeaways: ["a takeaway"],
    created_at: "2026-08-30T21:41:37.034678+00:00",
    updated_at: "2026-08-30T21:41:37.034678+00:00",
    ...overrides,
  };
}

function fetchFeedMock() {
  return fetchFeed as unknown as ReturnType<typeof vi.fn>;
}

function emptyPage(nextCursor: string | null) {
  return { cards: [], nextCursor, skipped: 0, requests: 1 };
}

function nonEmptyPage(cards: CardOut[], nextCursor: string | null) {
  return { cards, nextCursor, skipped: 0, requests: 1 };
}

beforeEach(() => {
  fetchFeedMock().mockReset();
});

describe("loadFeed empty-page drain", () => {
  it("T14: drains an empty-but-cursored page and returns a later non-empty page (live-verified fixture)", async () => {
    fetchFeedMock()
      .mockResolvedValueOnce(emptyPage(LIVE_CURSOR))
      .mockResolvedValueOnce(
        nonEmptyPage([fullCard({ card_id: "found-1" })], null),
      );

    const page = await loadFeed({ tag: "zzz-no-such-tag" });

    expect(fetchFeedMock()).toHaveBeenCalledTimes(2);
    expect(page.cards).toHaveLength(1);
    expect(page.cards[0].card_id).toBe("found-1");
    expect(page.nextCursor).toBeNull();
  });

  it("T15: each drain hop sends the previous page's next_cursor verbatim", async () => {
    const secondCursor = "second-cursor-token";
    fetchFeedMock()
      .mockResolvedValueOnce(emptyPage(LIVE_CURSOR))
      .mockResolvedValueOnce(emptyPage(secondCursor))
      .mockResolvedValueOnce(
        nonEmptyPage([fullCard({ card_id: "found-2" })], null),
      );

    await loadFeed({ tag: "zzz-no-such-tag" });

    const secondCallParams = fetchFeedMock().mock.calls[1][0];
    const thirdCallParams = fetchFeedMock().mock.calls[2][0];
    expect(secondCallParams.cursor).toBe(LIVE_CURSOR);
    expect(thirdCallParams.cursor).toBe(secondCursor);
  });

  it("T16: a non-empty short page returns after exactly one call, never drained", async () => {
    const shortPage = nonEmptyPage(
      [fullCard({ card_id: "a" }), fullCard({ card_id: "b" })],
      "some-live-cursor",
    );
    fetchFeedMock().mockResolvedValueOnce(shortPage);

    const page = await loadFeed();

    expect(fetchFeedMock()).toHaveBeenCalledTimes(1);
    expect(page.cards).toHaveLength(2);
    expect(page.nextCursor).toBe("some-live-cursor");
  });

  it("T17: stops at MAX_DRAIN_REQUESTS and returns the still-live cursor, never a 6th call", async () => {
    expect(MAX_DRAIN_REQUESTS).toBe(5);

    for (let i = 0; i < MAX_DRAIN_REQUESTS; i += 1) {
      fetchFeedMock().mockResolvedValueOnce(emptyPage(`cursor-${i}`));
    }
    fetchFeedMock().mockImplementation(() => {
      throw new Error("loadFeed must not issue a 6th drain request");
    });

    const page = await loadFeed({ tag: "zzz-no-such-tag" });

    expect(fetchFeedMock()).toHaveBeenCalledTimes(MAX_DRAIN_REQUESTS);
    expect(page.cards).toEqual([]);
    expect(page.nextCursor).toBe(`cursor-${MAX_DRAIN_REQUESTS - 1}`);
  });
});
