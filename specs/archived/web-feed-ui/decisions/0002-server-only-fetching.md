# ADR 0002: All `feed-api` fetching is server-side only

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-4, Guarantees 1 & 17
- **Trigger**: (a) explicit choice between named options; (b) constrains future features

## Context

The page needs `feed-api` data before it can render anything meaningful.
Next's App Router allows either a server-side fetch inside an async Server
Component, or a client-side fetch from a `"use client"` component using a
`NEXT_PUBLIC_*`-exposed base URL. The choice determines whether the browser
ever talks to `feed-api` directly, which in turn determines whether CORS is
actually exercised by this app.

## Decision

`app/page.tsx` is an async Server Component that `fetch`es `feed-api` from
Vercel's server and ships fully-rendered HTML. No component is marked
`"use client"` and fetches `feed-api`, and no `NEXT_PUBLIC_FEED_API_BASE_URL`
(or any `NEXT_PUBLIC_*` variable) exists anywhere in the app.

## Alternatives considered

| Option | Why not | 
|---|---|
| Expose `NEXT_PUBLIC_FEED_API_BASE_URL` and fetch from the browser | Would make CORS load-bearing (satisfying the intent's CORS acceptance criterion more literally), but at the cost of an empty-shell first paint (forbidden by the brief), plus client JS, a loading state, and a second failure mode the server-only path avoids entirely. |

## Consequences

**Positive**: The initial HTML response already contains the cards — no
loading spinner, no client-side data-fetching library needed, and
progressive enhancement is free (the feed works with JavaScript disabled,
since filtering/pagination are plain `<Link>`s). `FEED_API_BASE_URL` and any
future credential never reach the client bundle.

**Accepted costs**: The browser never issues a cross-origin request to
`feed-api` in this phase, so `feed-api`'s CORS allow-list update (performed
anyway, per the intent's Definition of Done) is forward-looking hygiene,
verified by `curl -H "Origin: …"` rather than by this app's own traffic —
stated honestly in contract.md's "Honest limitations" section rather than
treated as a defect.

## Follow-ups

Phase 3's chat UI (the next route in this same app, per ADR on app location)
is expected to be client-side/streaming and will be the first real consumer
of the CORS grant this feature puts in place.
