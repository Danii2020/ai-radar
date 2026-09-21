/**
 * Spec: web-feed-ui
 * Covers: T20-T26, T32, T33 (audit.md Test Coverage) / Guarantees 1, 4, 5,
 * 9, 10, 11 / AD-8, AD-11, AD-13 (contract.md) -- every branch of `FeedView`
 * is synchronous and prop-driven (AD-8), so it is fully unit-tested here.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FeedErrorCode, FeedPage } from "./client";
import { TAGLINE, WORDMARK, FeedView } from "./feed-view";
import { CHIP_NOTE } from "./tag-filter";
import type { CardOut } from "./types.generated";

afterEach(cleanup);

const ALL_STATE_TESTIDS = [
  "feed-list",
  "feed-empty",
  "feed-no-match",
  "feed-error",
];

function cardFixture(overrides: Partial<CardOut> = {}): CardOut {
  return {
    card_id: `card-${Math.random()}`,
    title: "A Card Title",
    url: "https://example.com/a",
    source: "Source",
    summary: "Summary",
    tags: ["llm"],
    type: "paper",
    relevance: 5,
    published: "2026-08-28",
    takeaways: ["a takeaway"],
    created_at: "2026-08-30T21:41:37.034678+00:00",
    updated_at: "2026-08-30T21:41:37.034678+00:00",
    ...overrides,
  };
}

function okPage(overrides: Partial<FeedPage> = {}): FeedPage {
  return { cards: [], nextCursor: null, skipped: 0, requests: 1, ...overrides };
}

function assertExactlyOneStateTestId(present: string) {
  for (const id of ALL_STATE_TESTIDS) {
    if (id === present) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    } else {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument();
    }
  }
}

describe("FeedView ordering", () => {
  it("T20: renders cards in the exact given order, never re-sorted", () => {
    const cards = [
      cardFixture({ card_id: "3", title: "Zebra Paper", relevance: 2 }),
      cardFixture({ card_id: "1", title: "Apple News", relevance: 9 }),
      cardFixture({ card_id: "2", title: "Mango Release", relevance: 5 }),
    ];
    const { container } = render(
      <FeedView state={{ status: "ok", page: okPage({ cards }) }} />,
    );

    const html = container.innerHTML;
    const positions = ["Zebra Paper", "Apple News", "Mango Release"].map(
      (title) => html.indexOf(title),
    );

    expect(positions.every((position) => position > -1)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });
});

describe("FeedView exhaustive states", () => {
  it("T21: renders feed-empty for zero cards, no tag, exhausted cursor", () => {
    render(<FeedView state={{ status: "ok", page: okPage() }} />);
    assertExactlyOneStateTestId("feed-empty");
  });

  it("T22: renders feed-no-match for zero cards with an active tag, with a clear link", () => {
    render(
      <FeedView
        state={{ status: "ok", page: okPage() }}
        tag="zzz-no-such-tag"
      />,
    );
    assertExactlyOneStateTestId("feed-no-match");
    expect(
      screen.getByRole("link", { name: /all cards/i }),
    ).toBeInTheDocument();
  });

  it.each<FeedErrorCode>(["config", "network", "http", "malformed"])(
    "T23: renders feed-error for code %s and leaks no status/base-url/stack text",
    (code) => {
      const { container } = render(
        <FeedView state={{ status: "error", code }} />,
      );

      assertExactlyOneStateTestId("feed-error");

      const text = container.textContent ?? "";
      for (const statusLike of ["400", "429", "500", "502", "503"]) {
        expect(text).not.toContain(statusLike);
      }
      expect(text).not.toContain("execute-api");
      expect(text).not.toContain("https://");
      expect(text).not.toMatch(/at .+:\d+:\d+/);
    },
  );

  it("T24: exactly one of the four state testids is present for a list render", () => {
    render(
      <FeedView state={{ status: "ok", page: okPage({ cards: [cardFixture()] }) }} />,
    );
    assertExactlyOneStateTestId("feed-list");
  });
});

describe("FeedView pagination", () => {
  it("T25: shows a Next page link iff nextCursor is not null, even on an empty page", () => {
    const { unmount } = render(
      <FeedView
        state={{ status: "ok", page: okPage({ nextCursor: "tok", requests: 5 }) }}
      />,
    );
    expect(
      screen.getByRole("link", { name: /next page/i }),
    ).toBeInTheDocument();
    unmount();

    render(
      <FeedView
        state={{
          status: "ok",
          page: okPage({ cards: [cardFixture()], nextCursor: null }),
        }}
      />,
    );
    expect(
      screen.queryByRole("link", { name: /next page/i }),
    ).not.toBeInTheDocument();
  });
});

describe("FeedView tag chips", () => {
  it("T26: tag chips are real /?tag= links and the active tag is always shown", () => {
    const cards = [cardFixture({ tags: ["llm", "agents"] })];
    render(
      <FeedView
        state={{ status: "ok", page: okPage({ cards }) }}
        tag="not-on-any-card"
      />,
    );

    const llmLink = screen.getByRole("link", { name: "llm" });
    expect(llmLink).toHaveAttribute("href", "/?tag=llm");

    expect(screen.getByText("not-on-any-card")).toBeInTheDocument();
  });
});

describe("FeedView masthead (AD-13)", () => {
  it("T32: WORDMARK and TAGLINE render in the list state", () => {
    render(
      <FeedView state={{ status: "ok", page: okPage({ cards: [cardFixture()] }) }} />,
    );
    expect(screen.getByText(WORDMARK)).toBeInTheDocument();
    expect(screen.getByText(TAGLINE)).toBeInTheDocument();
  });

  it("T32: WORDMARK and TAGLINE render in the empty state", () => {
    render(<FeedView state={{ status: "ok", page: okPage() }} />);
    expect(screen.getByText(WORDMARK)).toBeInTheDocument();
    expect(screen.getByText(TAGLINE)).toBeInTheDocument();
  });

  it("T32: WORDMARK and TAGLINE render in the no-match state", () => {
    render(
      <FeedView state={{ status: "ok", page: okPage() }} tag="zzz-no-such-tag" />,
    );
    expect(screen.getByText(WORDMARK)).toBeInTheDocument();
    expect(screen.getByText(TAGLINE)).toBeInTheDocument();
  });

  it("T32: WORDMARK and TAGLINE render in the error state", () => {
    render(<FeedView state={{ status: "error", code: "network" }} />);
    expect(screen.getByText(WORDMARK)).toBeInTheDocument();
    expect(screen.getByText(TAGLINE)).toBeInTheDocument();
  });
});

describe("FeedView tag-chip note (AD-11)", () => {
  it("T33: CHIP_NOTE renders verbatim wherever the chip row appears", () => {
    const cards = [cardFixture({ tags: ["llm"] })];
    render(<FeedView state={{ status: "ok", page: okPage({ cards }) }} />);

    expect(screen.getByText(CHIP_NOTE)).toBeInTheDocument();
  });
});
