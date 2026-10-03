/**
 * Spec: web-feed-ui
 * Covers: T4-T13 (audit.md Test Coverage) / Guarantees 2, 3, 8, 9, 12, 17 /
 * Error Handling Contract rows for config/network/http/malformed
 * (contract.md).
 *
 * `globalThis.fetch` is stubbed for every test -- this suite makes zero
 * network calls, per Guarantee 18.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  FeedApiError,
  REVALIDATE_SECONDS,
  fetchFeed,
  type FeedErrorCode,
} from "./client";
import type { CardOut } from "./types.generated";

const BASE_URL = "https://api.example.test";

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

interface MockResponseInit {
  ok: boolean;
  status?: number;
  jsonValue?: unknown;
  jsonRejects?: boolean;
}

function mockResponse({
  ok,
  status = ok ? 200 : 500,
  jsonValue,
  jsonRejects = false,
}: MockResponseInit) {
  return {
    ok,
    status,
    json: () =>
      jsonRejects
        ? Promise.reject(new SyntaxError("Unexpected token in JSON"))
        : Promise.resolve(jsonValue),
  };
}

function fetchMock() {
  return globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  vi.stubEnv("FEED_API_BASE_URL", BASE_URL);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function requestUrl(callIndex = 0): URL {
  const [urlArg] = fetchMock().mock.calls[callIndex];
  return new URL(String(urlArg));
}

function requestOptions(callIndex = 0): RequestInit & { next?: { revalidate?: number } } {
  const [, options] = fetchMock().mock.calls[callIndex];
  return options ?? {};
}

describe("fetchFeed request construction", () => {
  it("T4: issues exactly one request to <base>/v1/cards with limit always present", async () => {
    fetchMock().mockResolvedValueOnce(
      mockResponse({ ok: true, jsonValue: { cards: [], next_cursor: null } }),
    );

    await fetchFeed({ limit: 20 });

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    const url = requestUrl();
    expect(`${url.origin}${url.pathname}`).toBe(`${BASE_URL}/v1/cards`);
    expect(url.searchParams.get("limit")).toBe("20");
  });

  it("T5: includes tag/cursor iff non-empty; blank/whitespace tag is omitted", async () => {
    fetchMock().mockResolvedValue(
      mockResponse({ ok: true, jsonValue: { cards: [], next_cursor: null } }),
    );

    await fetchFeed({ tag: "agents", cursor: "tok123", limit: 20 });
    let url = requestUrl(0);
    expect(url.searchParams.get("tag")).toBe("agents");
    expect(url.searchParams.get("cursor")).toBe("tok123");

    await fetchFeed({ tag: "   ", limit: 20 });
    url = requestUrl(1);
    expect(url.searchParams.has("tag")).toBe(false);

    await fetchFeed({ limit: 20 });
    url = requestUrl(2);
    expect(url.searchParams.has("tag")).toBe(false);
    expect(url.searchParams.has("cursor")).toBe(false);
  });

  it("T6: a cursor round-trips byte-identically through URLSearchParams", async () => {
    const cursor =
      "eyJjYXJkX2lkIjoiOTgzMTAyYjNlYTNiNDM0MCIsImdzaV9wayI6IkNBUkQiLCJnc2lfc2siOiIwMDkjMjAyNi0wOC0yOCJ9";
    fetchMock().mockResolvedValueOnce(
      mockResponse({ ok: true, jsonValue: { cards: [], next_cursor: null } }),
    );

    await fetchFeed({ cursor, limit: 20 });

    const url = requestUrl();
    expect(url.searchParams.get("cursor")).toBe(cursor);
  });

  it("T7: passes next.revalidate === REVALIDATE_SECONDS", async () => {
    fetchMock().mockResolvedValueOnce(
      mockResponse({ ok: true, jsonValue: { cards: [], next_cursor: null } }),
    );

    await fetchFeed({ limit: 20 });

    const options = requestOptions();
    expect(options.next?.revalidate).toBe(REVALIDATE_SECONDS);
  });
});

describe("fetchFeed config failure", () => {
  it("T8: missing/blank FEED_API_BASE_URL throws FeedApiError('config') before any fetch", async () => {
    vi.stubEnv("FEED_API_BASE_URL", "");

    await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
      code: "config" satisfies FeedErrorCode,
    });
    expect(fetchMock()).not.toHaveBeenCalled();

    vi.stubEnv("FEED_API_BASE_URL", "   ");
    await expect(fetchFeed({ limit: 20 })).rejects.toBeInstanceOf(
      FeedApiError,
    );
    expect(fetchMock()).not.toHaveBeenCalled();
  });
});

describe("fetchFeed HTTP/network/malformed failures", () => {
  it.each([400, 429, 500])(
    "T9: a %i response throws FeedApiError('http') with status, no retry",
    async (status) => {
      fetchMock().mockResolvedValueOnce(
        mockResponse({ ok: false, status, jsonValue: { error: "boom" } }),
      );

      await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
        code: "http" satisfies FeedErrorCode,
        status,
      });
      expect(fetchMock()).toHaveBeenCalledTimes(1);
    },
  );

  it("T10: a rejected fetch promise throws FeedApiError('network')", async () => {
    fetchMock().mockRejectedValueOnce(new TypeError("network failure"));

    await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
      code: "network" satisfies FeedErrorCode,
    });
  });

  it("T11: a non-JSON body throws FeedApiError('malformed')", async () => {
    fetchMock().mockResolvedValueOnce(
      mockResponse({ ok: true, jsonRejects: true }),
    );

    await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
      code: "malformed" satisfies FeedErrorCode,
    });
  });

  it("T11: a non-object body throws FeedApiError('malformed')", async () => {
    fetchMock().mockResolvedValueOnce(
      mockResponse({ ok: true, jsonValue: "just a string" }),
    );

    await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
      code: "malformed" satisfies FeedErrorCode,
    });
  });

  it("T11: a body whose cards is not an array throws FeedApiError('malformed')", async () => {
    fetchMock().mockResolvedValueOnce(
      mockResponse({
        ok: true,
        jsonValue: { cards: "not-an-array", next_cursor: null },
      }),
    );

    await expect(fetchFeed({ limit: 20 })).rejects.toMatchObject({
      code: "malformed" satisfies FeedErrorCode,
    });
  });

  it("T12: a card failing isCardOut is dropped, skipped increments, good cards still return", async () => {
    const good = fullCard({ card_id: "good-1" });
    const bad = { card_id: "bad-1" }; // missing required string fields
    fetchMock().mockResolvedValueOnce(
      mockResponse({
        ok: true,
        jsonValue: { cards: [good, bad], next_cursor: null },
      }),
    );

    const page = await fetchFeed({ limit: 20 });

    expect(page.cards).toEqual([good]);
    expect(page.skipped).toBe(1);
  });
});

describe("fetchFeed next_cursor normalisation", () => {
  it.each([undefined, null, ""])(
    "T13: next_cursor %p normalises to nextCursor === null",
    async (nextCursorValue) => {
      const body: Record<string, unknown> = { cards: [] };
      if (nextCursorValue !== undefined) body.next_cursor = nextCursorValue;

      fetchMock().mockResolvedValueOnce(
        mockResponse({ ok: true, jsonValue: body }),
      );

      const page = await fetchFeed({ limit: 20 });
      expect(page.nextCursor).toBeNull();
    },
  );
});
