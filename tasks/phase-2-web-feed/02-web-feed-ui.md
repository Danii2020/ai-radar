# Spec 02 — Web feed UI

- **feature-name:** `web-feed-ui`
- **SDD target dir:** `specs/web-feed-ui/`
- **Depends on:** Spec 01 (`feed-api` — deployed API URL + `CardOut`/`FeedResponse` schema)
- **Layer:** Frontend

## Intent

A **Next.js** app, deployed on **Vercel's free tier**, that renders the
curated feed: cards sorted by relevance/date, filterable by tag, reading
through `feed-api`. This is design §8 Phase 2's actual deliverable — *"I can
open a URL and see them."*

## Background

`architecture-principles.md`'s Frontend section: "DDD is not a frontend
pattern. The Next.js app gets feature-folder organization and a typed client
generated from the `Card`/API contract. The domain lives behind the API; do
not mirror domain layers in the UI." This spec is greenfield — there is no
`apps/` directory yet in this repo; this is the first frontend code.

## Scope

**In scope**
- A new Next.js app (App Router), feature-folder organized (e.g. a
  `features/feed/` folder owning the feed's components, data-fetching, and
  types — not a generic `components/`/`services/` split mirroring backend
  layers).
- A **typed client** for `feed-api`, generated or hand-written directly from
  Spec 01's `CardOut`/`FeedResponse` contract (TypeScript types matching the
  Pydantic schema field-for-field). If Spec 01 exposes an OpenAPI schema,
  prefer generating from it; otherwise hand-author matching types and note
  the drift risk in contract.md.
- Feed view: cards sorted by relevance/date (server-rendered or
  static-with-revalidation — architect's call between SSR and ISR, but
  render on the server, don't ship an empty shell + client-side fetch as the
  primary path), rendering title, source, summary, tags, type, relevance,
  published date, and a link out to the original URL — the same fields the
  Phase 0/1 console `render()` in `src/shared/cards.py` already shows, now
  as a web UI.
- Tag filter UI: a control (e.g. a tag chip list or dropdown) that re-queries
  `feed-api` with `?tag=<x>`.
- Pagination UI consuming Spec 01's cursor (`next_cursor`) — "load more" or
  simple next-page, architect's call, but must not assume offset-based
  pagination.
- Empty/error states: no cards yet, API unreachable, tag with no matches —
  each renders something sane, not a blank page or an unhandled exception.
- Deployed to Vercel's free tier at a real, working URL, configured with the
  `feed-api` API Gateway URL as an environment variable (not hardcoded).
- `feed-api`'s CORS origin updated (or confirmed already covers) the real
  deployed Vercel URL — this spec's deploy step closes that loop with
  Spec 01.

**Out of scope**
- Chat / RAG UI (Phase 3).
- Auth, personalization, saved/favorited cards (Phase 4).
- A per-card detail/permalink page (deferred — see phase README scoping).
- Any AWS-side hosting (S3+CloudFront) — Vercel only, per the phase scoping
  decision.
- Any change to `feed-api`'s response contract — this spec consumes it
  as-is; if the contract is wrong/insufficient, that's a Spec 01 revision,
  not a workaround here.

## Contract sketch

```typescript
// feature-folder: features/feed/
interface CardOut {           // mirrors Spec 01's Pydantic schema exactly
  card_id: string;
  title: string;
  url: string;
  source: string;
  summary: string;
  tags: string[];
  type: string;
  relevance: number;
  published: string;
  takeaways: string[];
  created_at: string;
  updated_at: string;
}

interface FeedResponse {
  cards: CardOut[];
  next_cursor: string | null;
}

async function fetchFeed(params: { tag?: string; cursor?: string; limit?: number }): Promise<FeedResponse>;
```

## Acceptance criteria

- [ ] Loading the deployed Vercel URL renders the real, current
      `ai-radar-cards` feed — not mock/seed data — sorted by
      relevance/date.
- [ ] Selecting a tag filter re-renders the feed to only cards carrying that
      tag, via a real `feed-api` call (not a client-side filter of an
      already-fetched full set).
- [ ] Pagination (via `next_cursor`) reaches cards beyond the first page
      with no duplicates or gaps.
- [ ] Empty feed, tag-with-no-matches, and `feed-api`-unreachable each
      render a distinct, sane UI state (verified in tests/manually, not just
      asserted in prose).
- [ ] The typed client's types match Spec 01's `CardOut`/`FeedResponse`
      field-for-field — a contract drift here is a bug, not a nit.
- [ ] Deployed on Vercel at a real URL; `feed-api`'s CORS is confirmed
      (curl or browser network tab) to accept requests from that exact
      origin.
- [ ] No domain/aggregate/repository layering introduced in the UI —
      feature-folder only, per `architecture-principles.md`.

## SDD note

Feed to `sdd-architect` as `web-feed-ui`, only after Spec 01 (`feed-api`) is
deployed — the architect needs a real API URL and real response shapes to
design against, not a mock. The contract must lock the typed client's
field-for-field parity with Spec 01's schema as a hard guarantee, since drift
between the two is the main risk of splitting API and UI into separate
specs.
