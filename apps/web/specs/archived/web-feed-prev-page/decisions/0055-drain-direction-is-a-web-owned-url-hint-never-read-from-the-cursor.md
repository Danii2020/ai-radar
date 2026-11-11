# ADR 0055: The drain direction is a web-owned `dir=prev` URL hint, never read from the opaque cursor

- **Status**: Accepted. Amends ADR 0004 for backward requests (drain follows `prev_cursor`); the ADR 0004 file is not edited, and its status stays Accepted.
- **Date**: 2026-11-10
- **Feature**: web-feed-prev-page
- **Capability**: web-feed
- **Source**: execution-plan.md § Proposed approach (the first "Decision" bullet, its "Rejected" list, and the "ADR candidate (0055)" bullet); § Binding constraints (drain direction rule table)
- **Trigger**: (a) it chooses between named options (drain only `next_cursor`; infer the direction from the response; decode the cursor; send a direction to `feed-api`); (b) it is a rule later features must obey (cursors stay opaque, `dir` is never forwarded to `feed-api`); (c) it diverges from ADR 0004 for backward requests

## Context

`feed-api` returns `prev_cursor` on every 200 (ADR 0051, feed-prev-cursor). A reader who presses `‹ Previous page` lands on a backward page, and a tag filter can make that page empty. The web drain (ADR 0004) follows `next_cursor` over empty pages. On a backward page, `next_cursor` points forward at the far end of the stretch just read. Following it would turn the drain around and walk the reader forward again, so Previous could never cross a gap of empty filtered pages.

The web app has to know which pointer to follow, and it may not decode the cursor (WEB-3, invariant 2). A forward page reached by cursor and a backward page both carry two non-null cursors, so the response cannot tell them apart.

## Decision

A backward request is marked by the web app's own URL hint `dir=prev`, present only on the Previous link and only together with a non-empty `cursor`. The loader drains along `prev_cursor` for that request and along `next_cursor` for every other request. The hint is parsed from the URL, threaded to the loader, and never sent to `feed-api`. Cursors remain opaque bytes.

## Alternatives considered

| Option | Why not |
|---|---|
| Drain only ever follows `next_cursor` | On an empty backward page, `next_cursor` leads forward to the far end of the stretch. The drain turns round toward the page the reader left, so Previous cannot cross an empty filtered gap. A navigation trap. |
| Show empty backward pages undrained | Live tag filters at page size 5 produce empty pages often, so Previous would show a "no matches" state between two non-empty pages. WEB-4 exists to prevent exactly that. |
| Infer the direction from the response | A forward page and a backward page both carry two non-null cursors (FA-7), so the response cannot tell them apart. |
| Decode a direction marker inside the cursor | Forbidden by WEB-3 and invariant 2. It would couple the web app to the backend's private token shape, which ADR 0051 keeps opaque. |
| Send a `?direction=` parameter to `feed-api` | The backend has no such parameter (rejected in root `feed-prev-cursor`). |

## Consequences

**Positive**: Previous crosses empty filtered pages in the reader's direction and never skips a card. Bookmarks, shared links and the browser Back button keep working, because the hint is plain URL state (ADR 0003). Without `dir`, every request behaves as before. A forged `dir=prev` on a forward cursor can change only which server-issued pointer an empty page follows. It cannot skip a card or exceed the 5-request cap.

**Accepted costs**: The web app now relies on a second server-issued pointer for backward drains. Filtered backward page boundaries may differ from the forward ones (FA-R2, accepted by the human), and the web app does not compensate for this. A forged `dir=prev` can show an earlier page than the reader expected. The drain stays bounded by `MAX_DRAIN_REQUESTS` (5) in both directions.

## Follow-ups

None. If `feed-api` ever exposes an explicit direction, this hint could be retired in favour of it, which would need a new decision.
