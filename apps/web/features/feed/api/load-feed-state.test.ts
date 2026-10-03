/**
 * Spec: feed-structure-refactor
 * Covers: AC5 -- loadFeedState maps loadFeed's outcome to a FeedViewState,
 * never throws, and writes the single `feed_fetch_failed` line page.tsx used
 * to write (same keys, same order, undefined omitted, no cursor value, no
 * error message).
 *
 * `loadFeed` (from `./load-feed`) is mocked: the drain logic is covered by
 * load-feed.test.ts. `FeedApiError` is the real class.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedPage } from "./client";

vi.mock("./load-feed", () => ({
  loadFeed: vi.fn(),
}));

import { FeedApiError } from "./client";
import { loadFeed } from "./load-feed";
import { loadFeedState } from "./load-feed-state";

const mockedLoadFeed = vi.mocked(loadFeed);

const PAGE: FeedPage = { cards: [], nextCursor: "next", skipped: 0, requests: 2 };

let errorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  mockedLoadFeed.mockReset();
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  errorSpy.mockRestore();
});

describe("loadFeedState: success", () => {
  it("returns ok with exactly the page loadFeed resolved with, and logs nothing", async () => {
    mockedLoadFeed.mockResolvedValue(PAGE);

    const state = await loadFeedState({ tag: "agents", cursor: "abc" });

    expect(state).toEqual({ status: "ok", page: PAGE });
    if (state.status === "ok") expect(state.page).toBe(PAGE);
    expect(mockedLoadFeed).toHaveBeenCalledWith({ tag: "agents", cursor: "abc" });
    expect(errorSpy).not.toHaveBeenCalled();
  });
});

describe("loadFeedState: failure", () => {
  it.each(["config", "network", "http", "malformed"] as const)(
    "a FeedApiError with code %s returns that code",
    async (code) => {
      mockedLoadFeed.mockRejectedValue(new FeedApiError(code, "boom"));

      await expect(loadFeedState({})).resolves.toEqual({ status: "error", code });
    },
  );

  it("any other thrown value returns code network", async () => {
    for (const thrown of [new TypeError("x"), "a string", undefined, null, 42]) {
      mockedLoadFeed.mockRejectedValueOnce(thrown);
      await expect(loadFeedState({})).resolves.toEqual({
        status: "error",
        code: "network",
      });
    }
  });

  it("logs exactly one line for a FeedApiError, with status, tag and has_cursor in order", async () => {
    mockedLoadFeed.mockRejectedValue(new FeedApiError("http", "secret detail", 503));

    const state = await loadFeedState({ tag: "agents", cursor: "abc" });

    expect(state).toEqual({ status: "error", code: "http" });
    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      '{"event":"feed_fetch_failed","code":"http","status":503,"tag":"agents","has_cursor":true}',
    );
  });

  it("omits undefined keys and reports code network for a non-FeedApiError", async () => {
    mockedLoadFeed.mockRejectedValue(new TypeError("x"));

    await loadFeedState({});

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      '{"event":"feed_fetch_failed","code":"network","has_cursor":false}',
    );
  });

  it("omits status for a FeedApiError that has none", async () => {
    mockedLoadFeed.mockRejectedValue(new FeedApiError("malformed", "bad json"));

    await loadFeedState({ tag: "llm" });

    expect(errorSpy).toHaveBeenCalledWith(
      '{"event":"feed_fetch_failed","code":"malformed","tag":"llm","has_cursor":false}',
    );
  });

  it("never logs the cursor value or the error message", async () => {
    mockedLoadFeed.mockRejectedValue(new FeedApiError("http", "leaky-message-123", 500));

    await loadFeedState({ tag: "agents", cursor: "secret-cursor-value" });

    const line = String(errorSpy.mock.calls[0][0]);
    expect(line).not.toContain("secret-cursor-value");
    expect(line).not.toContain("leaky-message-123");
  });
});
