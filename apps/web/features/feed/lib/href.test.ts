/**
 * Spec: web-feed-ui
 * Covers: T18 (audit.md Test Coverage) / Guarantee 3, 5 / AD-5
 * (contract.md) -- `feedHref` is the single place a feed URL is built;
 * cursors pass through untouched in value, encoded only for transit.
 */
import { describe, expect, it } from "vitest";
import { feedHref } from "./href";

describe("feedHref", () => {
  it("T18: returns '/' when no params are given", () => {
    expect(feedHref()).toBe("/");
    expect(feedHref({})).toBe("/");
  });

  it("T18: includes only tag when cursor is absent", () => {
    expect(feedHref({ tag: "agents" })).toBe("/?tag=agents");
  });

  it("T18: includes both tag and cursor; the cursor value round-trips identically", () => {
    const cursor = "abc==";
    const href = feedHref({ tag: "agents", cursor });

    expect(href.startsWith("/?")).toBe(true);
    const url = new URL(href, "https://example.test");
    expect(url.searchParams.get("tag")).toBe("agents");
    expect(url.searchParams.get("cursor")).toBe(cursor);
  });

  it("T18: never produces '?tag=' for a null, undefined, or empty tag", () => {
    expect(feedHref({ tag: null })).toBe("/");
    expect(feedHref({ tag: undefined })).toBe("/");
    expect(feedHref({ tag: "" })).toBe("/");

    expect(feedHref({ tag: null })).not.toContain("tag=");
    expect(feedHref({ tag: undefined })).not.toContain("tag=");
    expect(feedHref({ tag: "" })).not.toContain("tag=");
  });

  it("T18: never produces '?cursor=' for a null, undefined, or empty cursor", () => {
    expect(feedHref({ tag: "agents", cursor: null })).toBe("/?tag=agents");
    expect(feedHref({ tag: "agents", cursor: undefined })).toBe(
      "/?tag=agents",
    );
    expect(feedHref({ tag: "agents", cursor: "" })).toBe("/?tag=agents");
  });
});
