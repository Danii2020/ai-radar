# ADR 0003: Pagination is URL cursor links, not client-side "load more"

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-5, Guarantee 3, Guarantee 5
- **Trigger**: (a) explicit choice between named options; (b) constrains future features

## Context

`feed-api` returns an opaque `next_cursor`. The UI needs a pagination
mechanism, and the natural alternatives are a server-rendered "next page"
link (each page its own URL) versus a client-side "load more" button that
accumulates cards in memory.

## Decision

Each page is addressed by its own URL: `/?tag=<t>&cursor=<opaque>`. "Next
page →" is a `<Link>` carrying the cursor verbatim (URL-encoded in transit,
byte-identical in value). Nothing in the UI parses, decodes, constructs, or
compares a cursor anywhere.

## Alternatives considered

| Option | Why not |
|---|---|
| Accumulating "Load more" button | Needs `"use client"`, a client-side fetch (reversing the server-only-fetching decision), a growing in-memory list, and a scroll-restoration story — real cost for a 5-page feed. Cursor opacity is respected either way; the link-based approach costs nothing extra. |

## Consequences

**Positive**: Browser Back works for free (no client state to restore).
Every page is server-rendered, shareable, and crawlable. Zero client state
for pagination.

**Accepted costs**: No "Previous" link exists — cursor pagination is
forward-only by nature, and browser Back is the answer (each page being its
own URL is what makes that work). No page numbers, since cursor pagination
has none to show.

## Follow-ups

None.
