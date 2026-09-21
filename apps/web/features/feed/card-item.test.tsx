/**
 * Spec: web-feed-ui
 * Covers: T27, T28 (audit.md Test Coverage) / Guarantee 9 / AD-7
 * (contract.md) -- the HTML port of `render()` in `src/shared/cards.py`.
 *
 * Amendment (2026-09-18, human-approved): contract.md's Data Models
 * field-rendering table renders `url` as "the heading's href + a visible
 * link line" (feed.module.css's unused `.urlLine`, the design mockup's
 * URL line under the title). card-item.tsx therefore always renders TWO
 * anchors -- the title link and a second link whose accessible name is
 * the URL itself -- independent of tags/takeaways. T27 asserts the second
 * link's href/text/target/rel; T28's link-count assertion is 2, not 1.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CardItem } from "./card-item";
import type { CardOut } from "./types.generated";

afterEach(cleanup);

function fullCard(overrides: Partial<CardOut> = {}): CardOut {
  return {
    card_id: "card-full",
    title: "AI agents rapidly exploit security vulnerabilities",
    url: "https://simonwillison.net/2026/Aug/28/just-a-rumour-of-a-bug/",
    source: "Simon Willison",
    summary: "Modern AI coding agents can now discover and exploit bugs.",
    tags: ["security", "ai-agents", "vulnerability"],
    type: "paper",
    relevance: 9,
    published: "2026-08-28",
    takeaways: ["First takeaway", "Second takeaway", "Third takeaway"],
    created_at: "2026-08-30T21:41:37.034678+00:00",
    updated_at: "2026-08-30T21:41:37.034678+00:00",
    ...overrides,
  };
}

describe("CardItem full fixture", () => {
  it("T27: renders title/source/summary/tags/takeaways/type/relevance/published, and the title links out correctly", () => {
    const card = fullCard();
    const { container } = render(<CardItem card={card} />);

    const titleLink = screen.getByRole("link", { name: card.title });
    expect(titleLink).toHaveAttribute("href", card.url);
    expect(titleLink).toHaveAttribute("target", "_blank");
    expect(titleLink).toHaveAttribute("rel", "noopener noreferrer");

    // The visible URL line (contract.md: url -> "the heading's href + a
    // visible link line") is a second, distinct anchor -- its accessible
    // name is the URL itself, not the title.
    const urlLink = screen.getByRole("link", { name: card.url });
    expect(urlLink).not.toBe(titleLink);
    expect(urlLink).toHaveAttribute("href", card.url);
    expect(urlLink).toHaveAttribute("target", "_blank");
    expect(urlLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(urlLink.textContent).toContain(card.url);

    const text = container.textContent ?? "";
    expect(text).toContain(card.source);
    expect(text).toContain(card.summary);
    for (const tag of card.tags ?? []) {
      expect(text).toContain(tag);
    }
    for (const takeaway of card.takeaways ?? []) {
      expect(text).toContain(takeaway);
    }
    expect(text).toContain(card.type);
    expect(text).toContain(`relevance ${card.relevance}/10`);
    expect(text).toContain(card.published);
  });
});

describe("CardItem optional-field and unknown-type resilience", () => {
  it("T28: tags and takeaways undefined render without throwing and without chip/bullet markup", () => {
    const card = fullCard({ tags: undefined, takeaways: undefined });

    let result: ReturnType<typeof render> | undefined;
    expect(() => {
      result = render(<CardItem card={card} />);
    }).not.toThrow();

    // The title anchor AND the always-present URL-line anchor exist -- no
    // tag-chip links (tags is undefined). Both links are independent of
    // tags/takeaways, unlike chips/bullets.
    expect(screen.getAllByRole("link")).toHaveLength(2);
    // No bulleted-list markup for takeaways.
    expect(result?.container.querySelectorAll("li")).toHaveLength(0);
  });

  it('T28: published === "" renders "date n/a"', () => {
    const card = fullCard({ published: "" });

    render(<CardItem card={card} />);

    expect(screen.getByText(/date n\/a/i)).toBeInTheDocument();
  });

  it("T28: an unrecognised type renders without throwing and sets data-type verbatim", () => {
    const card = fullCard({ type: "mystery" });

    let result: ReturnType<typeof render> | undefined;
    expect(() => {
      result = render(<CardItem card={card} />);
    }).not.toThrow();

    expect(
      result?.container.querySelector('[data-type="mystery"]'),
    ).not.toBeNull();
  });
});
