# ADR 0006: Explicit 300s revalidate on the feed fetch; keep the AbortSignal timeout

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-9
- **Trigger**: (d) accepts a known, deliberately-recorded cost/unverifiable claim

## Context

Next 15/16 do not cache `fetch` by default, and a route reading
`searchParams` is dynamic — so without an explicit caching option, every
page view is a fresh, billed `feed-api` request. `feed-api`'s own AD-7 named
request-count billing as its accepted residual cost risk; this spec must not
silently amplify it. Separately, a hung upstream call should not hold a
render open for API Gateway's full 30-second limit.

Whether `AbortSignal.timeout(...)` (added for the second concern) interacts
badly with Next's persistent Data Cache (i.e. whether it silently disables
the caching from the first concern) was not settled by Next's documentation,
and the spec explicitly deferred resolving it to "running it, not arguing
about it" (house style, mirroring `feed-api`'s AD-6).

## Decision

`fetchFeed()` passes `{ next: { revalidate: REVALIDATE_SECONDS } }` (300s —
curation runs once daily, so this is always fresher than the data actually
is) **and** `signal: AbortSignal.timeout(FETCH_TIMEOUT_MS)` (8s) on every
request. After a documentation pass (Next 16's fetch reference: `signal`
opts a request out of per-render *memoization*, a distinct and
shorter-lived mechanism from the persistent Data Cache driven by
`next.revalidate` — no documented interaction between the two was found in
either direction) and Task 4.11's live local dev-server check not producing
a direct repeat-view cache-hit observation, the human made a final,
deliberate call: **keep `signal`**, and accept the open question as
resolved-by-acceptance rather than continuing to investigate it.

## Alternatives considered

| Option | Why not |
|---|---|
| Drop `signal`, keep only `revalidate` | Would remove the 8s render-time bound entirely, relying only on the Lambda's own 10s timeout plus API Gateway's 30s — a real regression in render responsiveness for no confirmed caching benefit, and the risk of `signal` disabling caching was never actually confirmed, only left unconfirmed. |
| Keep investigating (e.g. add temporary logging, instrument a live repeat-view test) before accepting | Diminishing returns: worst case if `signal` does disable Data Cache is uncached views — which are already bounded by `MAX_DRAIN_REQUESTS` (ADR 0004) and backstopped by the pre-existing `AiRadarBudget` CloudWatch alarms from an earlier feature. The one-line revert (drop `signal`) remains available at any time this changes. |

## Consequences

**Positive**: A hung `feed-api` call cannot hold a Vercel render open longer
than 8s. Repeat views of an identical URL within 5 minutes *may* avoid a
second upstream request, damping burst traffic.

**Accepted costs**: It is not empirically confirmed, only documentation-
researched, whether the 300s caching is actually effective in the presence
of `signal`. This is recorded as `WEB-R2` in the `web-feed` capability
doc's open reservations — an accepted, non-blocking risk, not silently
dropped.

## Follow-ups

If a future session ever does confirm (via live repeat-view request
counting) that `signal` disables the Data Cache, the fix is a one-line
removal of the `signal` option — no design change required.
