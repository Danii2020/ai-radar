# Current-State Specifications — apps/web (frontend)

> Current truth for the Next.js frontend. Maintained by `harny-sync`; do not hand-edit.
> Last synced: 2026-11-11 (web-chat-swipe-handle archived: `web-chat` WEBCHAT-1 amended, WEBCHAT-12 widened, WEBCHAT-13 added, ADR 0056, reservations WEBCHAT-R10 and R11; `web-feed` WEB-9 pointer moved, WEB-R9). Earlier: 2026-11-10 (web-feed-prev-page archived: `web-feed` WEB-3, WEB-4 and WEB-7 amended, ADR 0055, reservations WEB-R5 to WEB-R8). Earlier: 2026-10-24 (web-chat-ui and web-chat-ui-polish archived: new `web-chat` capability, ADRs 0032–0039; earlier: feed-structure-refactor archived, component split — this index was carved out of the
> repo-root `specs/current/_index.md` when `apps/web/` got its own harny harness,
> `stack: typescript`; see Notes)

> **Two harness roots.** This index covers `apps/web/` only. The Python backend
> (curation pipeline, card store, runtime, scheduling, observability, `feed-api`)
> is indexed at the repo root: [`../../../../specs/current/_index.md`](../../../../specs/current/_index.md).
> `web-feed` consumes the backend's `feed-api` capability — read
> [`feed-api.md`](../../../../specs/current/feed-api.md) for the contract it depends on.

## Capabilities

| Capability | Current-State Specification | Incorporated Changes |
|---|---|---|
| web-feed | [web-feed.md](./web-feed.md) | [web-feed-ui](../archived/web-feed-ui/), [feed-structure-refactor](../archived/feed-structure-refactor/), [web-chat-ui](../archived/web-chat-ui/) (amendments), [web-chat-ui-polish](../archived/web-chat-ui-polish/) (amendments), [web-feed-prev-page](../archived/web-feed-prev-page/) (WEB-3, WEB-4, WEB-7 amendments), [web-chat-swipe-handle](../archived/web-chat-swipe-handle/) (WEB-9 pointer, `.pagerLink` CSS) |
| web-chat | [web-chat.md](./web-chat.md) | [web-chat-ui](../archived/web-chat-ui/), [web-chat-ui-polish](../archived/web-chat-ui-polish/), [web-chat-swipe-handle](../archived/web-chat-swipe-handle/) |

## Keyword lookup

> If your question mentions a term on the left, read the capability on the right first.

| Term | Capability |
|---|---|
| cursor / next_cursor pagination | web-feed (backend side: root `specs/current/feed-api.md`) |
| tag filter | web-feed (backend side: root `specs/current/feed-api.md`) |
| Next.js / App Router | web-feed |
| apps/web | web-feed |
| types.generated.ts / codegen drift | web-feed |
| FeedView / feed-list / feed-error | web-feed |
| cursor drain / MAX_DRAIN_REQUESTS | web-feed |
| CSS Modules / tokens.css / feed.module.css | web-feed |
| Vercel deploy | web-feed |
| features/feed/index.ts / barrel / api-components-lib layout | web-feed |
| Playwright / test:e2e / e2e baseline | web-feed |
| loadFeedState / parseFeedSearchParams | web-feed |
| server-only fetch / "use client" | web-feed, web-chat |
| chat widget / floating button / ChatWidget | web-chat |
| /api/chat route / handleChatRequest / six error codes | web-chat |
| SigV4 / aws4fetch / CHAT_API_* env | web-chat (backend side: root `specs/current/chat-api-auth.md`) |
| react-markdown / safe markdown / use-stick-to-bottom | web-chat |
| bottom sheet / phone layout / Jump to latest | web-chat |
| edge tab / swipe / classifySwipe / touch gesture / allowedDevOrigins | web-chat (ADR 0056) |
| design deliverable revision / `.urlLine` / WEB-9 | web-feed |
| Previous page / `‹ Previous page` / prev_cursor | web-feed (backend side: root `specs/current/feed-api.md`) |
| dir=prev / backward drain / drain direction | web-feed (ADR 0055) |

## Synchronized Changes

| Change | Archive | Current-State Specification |
|---|---|---|
| web-feed-ui | [specs/archived/web-feed-ui/](../archived/web-feed-ui/) | [web-feed.md](./web-feed.md) |
| feed-structure-refactor | [specs/archived/feed-structure-refactor/](../archived/feed-structure-refactor/) | [web-feed.md](./web-feed.md) |
| web-chat-ui | [specs/archived/web-chat-ui/](../archived/web-chat-ui/) | [web-chat.md](./web-chat.md), [web-feed.md](./web-feed.md) |
| web-chat-ui-polish | [specs/archived/web-chat-ui-polish/](../archived/web-chat-ui-polish/) | [web-chat.md](./web-chat.md), [web-feed.md](./web-feed.md) |
| web-feed-prev-page | [specs/archived/web-feed-prev-page/](../archived/web-feed-prev-page/) | [web-feed.md](./web-feed.md) (WEB-3, WEB-4 amended; WEB-7 refreshed; WEB-R5 to WEB-R8) |
| web-chat-swipe-handle | [specs/archived/web-chat-swipe-handle/](../archived/web-chat-swipe-handle/) | [web-chat.md](./web-chat.md) (WEBCHAT-1 amended, WEBCHAT-12 widened, WEBCHAT-13; WEBCHAT-R10, R11), [web-feed.md](./web-feed.md) (WEB-9 pointer; WEB-R9) |

## Decisions (ADR registry)

ADR numbers are **repo-wide monotonic** across both harness roots (this one and
the repo root's). The next ADR written in either harness is **0057**. ADRs 0040, 0042–0048 and 0051–0054 are taken by the repo-root harness; 0049 and 0050 are claimed by `web-chat-visitor-rate-limit` (not yet archived); 0055 was written by `web-feed-prev-page` and 0056 by `web-chat-swipe-handle`; 0041 was never promoted. (ADRs 0009–0031 were written by the repo-root harness; see its index.)

| ADR | Title | Status | Capability | Path |
|---|---|---|---|---|
| 0001 | Generate TypeScript types from the schema artifact, never hand-author them | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md](../archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md) |
| 0002 | All `feed-api` fetching is server-side only | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0002-server-only-fetching.md](../archived/web-feed-ui/decisions/0002-server-only-fetching.md) |
| 0003 | Pagination is URL cursor links, not client-side "load more" | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0003-url-cursor-pagination.md](../archived/web-feed-ui/decisions/0003-url-cursor-pagination.md) |
| 0004 | Drain empty-but-cursored pages, bounded to 5 requests | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md](../archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md) |
| 0005 | Styling is CSS Modules, copied byte-verbatim from hand-authored design deliverables | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md](../archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md) |
| 0006 | Explicit 300s revalidate on the feed fetch; keep the AbortSignal timeout | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md](../archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md) |
| 0007 | Deployment is a human-run step; the automated pipeline stops at local verification | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md](../archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md) |
| 0008 | Split the feed feature by role behind one public entry point, verified by an offline Playwright baseline | Accepted | web-feed | [specs/archived/feed-structure-refactor/decisions/0008-feed-feature-split-by-role-behind-one-entry-point.md](../archived/feed-structure-refactor/decisions/0008-feed-feature-split-by-role-behind-one-entry-point.md) |
| 0032 | Sign chat requests with aws4fetch `sign()` and our own single `fetch` | Accepted | web-chat | [specs/archived/web-chat-ui/decisions/0032-sign-with-aws4fetch-sign-and-our-own-single-fetch.md](../archived/web-chat-ui/decisions/0032-sign-with-aws4fetch-sign-and-our-own-single-fetch.md) |
| 0033 | The Next.js route is the only chat caller, and it answers with six fixed error codes | Accepted | web-chat | [specs/archived/web-chat-ui/decisions/0033-the-next-route-is-the-only-chat-caller-with-fixed-error-codes.md](../archived/web-chat-ui/decisions/0033-the-next-route-is-the-only-chat-caller-with-fixed-error-codes.md) |
| 0034 | Narrow the `execute-api` guard to the host form | Accepted | web-chat | [specs/archived/web-chat-ui/decisions/0034-narrow-the-execute-api-guard-to-the-host-form.md](../archived/web-chat-ui/decisions/0034-narrow-the-execute-api-guard-to-the-host-form.md) |
| 0035 | No per-visitor limit on the chat route in v1 | Accepted | web-chat | [specs/archived/web-chat-ui/decisions/0035-no-per-visitor-limit-on-the-chat-route-in-v1.md](../archived/web-chat-ui/decisions/0035-no-per-visitor-limit-on-the-chat-route-in-v1.md) |
| 0036 | Build AI-Elements-shaped local components, not shadcn/ui or AI Elements | Accepted | web-chat | [specs/archived/web-chat-ui-polish/decisions/0036-ai-elements-shaped-local-components-not-shadcn-or-ai-elements.md](../archived/web-chat-ui-polish/decisions/0036-ai-elements-shaped-local-components-not-shadcn-or-ai-elements.md) |
| 0037 | Amend the dependency rule for `react-markdown` and `use-stick-to-bottom` | Accepted | web-chat | [specs/archived/web-chat-ui-polish/decisions/0037-dependency-rule-amended-for-react-markdown-and-use-stick-to-bottom.md](../archived/web-chat-ui-polish/decisions/0037-dependency-rule-amended-for-react-markdown-and-use-stick-to-bottom.md) |
| 0038 | Assistant markdown renders through a safe subset | Accepted | web-chat | [specs/archived/web-chat-ui-polish/decisions/0038-assistant-markdown-renders-through-a-safe-subset.md](../archived/web-chat-ui-polish/decisions/0038-assistant-markdown-renders-through-a-safe-subset.md) |
| 0039 | Design deliverable revisions live with the feature that makes them | Accepted | web-feed | [specs/archived/web-chat-ui-polish/decisions/0039-deliverable-revisions-live-with-the-feature.md](../archived/web-chat-ui-polish/decisions/0039-deliverable-revisions-live-with-the-feature.md) |
| 0055 | The drain direction is a web-owned `dir=prev` URL hint, never read from the opaque cursor (amends 0004 for backward requests) | Accepted | web-feed | [specs/archived/web-feed-prev-page/decisions/0055-drain-direction-is-a-web-owned-url-hint-never-read-from-the-cursor.md](../archived/web-feed-prev-page/decisions/0055-drain-direction-is-a-web-owned-url-hint-never-read-from-the-cursor.md) |
| 0056 | On phones the chat launcher is a 24 by 64 px edge tab with threshold touch and pen swipes (amends WEBCHAT-1's 44 px hit area at 640 px and narrower) | Accepted | web-chat | [specs/archived/web-chat-swipe-handle/decisions/0056-phone-chat-launcher-is-a-24-by-64-edge-tab-with-threshold-swipes.md](../archived/web-chat-swipe-handle/decisions/0056-phone-chat-launcher-is-a-24-by-64-edge-tab-with-threshold-swipes.md) |

## Open reservations

> Non-blocking findings accepted at ship time and still open.

| ID | Reservation | Severity | Source | Capability |
|---|---|---|---|---|
| WEB-R1 | Not yet deployed: no Vercel project exists, and `feed-api`'s CORS allow-list has not been updated to a real Vercel origin. Locally verified only, not live. | HIGH (operational, expected — Phase 5 is human-gated by design) | `specs/archived/web-feed-ui/audit.md` | web-feed |
| WEB-R2 | Whether `AbortSignal.timeout` on the feed fetch disables Next's Data Cache was researched but never empirically confirmed live. Accepted as final, not reopened. | LOW (accepted) | `specs/archived/web-feed-ui/audit.md` AD-9/C25 | web-feed |
| WEB-R3 | `conventions.test.ts`'s no-`NEXT_PUBLIC_`/no-`execute-api` guard scans only `features/**`/`app/**`, not `scripts/`/`*.mjs`/`*.mts`/configs — narrower than its own description, no violation exists today. | LOW | `specs/archived/web-feed-ui/audit.md` | web-feed |
| WEB-R4 | Duplicate web workflow resolved (the hand-relocated `harny-feedback-web.yml` was removed; `harny-feedback-apps-web.yml` is kept). No green CI run exists against the refactor yet. | LOW | `specs/archived/feed-structure-refactor/audit.md` F3 | web-feed |
| WEBCHAT-R1 | No per-visitor limit on `/api/chat`; the shared throttle can be used up by one visitor (ADR 0035). | MEDIUM (accepted) | `specs/archived/web-chat-ui/execution-plan.md` | web-chat |
| WEBCHAT-R2 | Not exercised against the real API; the human live check (H1) is open. | LOW (human) | `specs/archived/web-chat-ui/audit.md` F7 | web-chat |
| WEBCHAT-R3 | Vercel function duration vs `maxDuration` 40 unchecked; `CHAT_API_*` not set in Vercel (H2). | LOW (human) | `specs/archived/web-chat-ui/audit.md` | web-chat |
| WEBCHAT-R4 | A blank history `text` passes the route and is rejected by the backend. | MEDIUM | `specs/archived/web-chat-ui/audit.md` F1 | web-chat |
| WEBCHAT-R5 | UTF-16 vs code-point length counting; late body cap without `Content-Length`; body-read abort maps to `upstream_failure`. | LOW | `specs/archived/web-chat-ui/audit.md` F3–F5 | web-chat |
| WEBCHAT-R6 | Source links unfiltered by scheme; image inside a link leaves an unnamed `<a>`. | LOW | `specs/archived/web-chat-ui-polish/audit.md` F8 | web-chat |
| WEBCHAT-R7 | No green CI run of `harny-feedback-apps-web.yml` against the chat work (also `web-chat-swipe-handle`); no per-turn hook evidence. | MEDIUM | `specs/archived/web-chat-ui/audit.md` F6; `web-chat-ui-polish/audit.md` F2 | web-chat |
| WEBCHAT-R8 | Red evidence missing for polish outcomes O5–O8; shell freeze rests on mtimes. | LOW | `specs/archived/web-chat-ui-polish/audit.md` F4, F6 | web-chat |
| WEBCHAT-R9 | Launcher `aria-controls` names an unmounted id while closed; a draft edited while pending is overwritten on failure. | LOW | `specs/archived/web-chat-ui/audit.md` F8, F10 | web-chat |
| WEB-R5 | No green CI run of `harny-feedback-apps-web.yml` against the previous-page work yet, and no `apps/web` per-turn hook record for its edits. | LOW | `specs/archived/web-feed-prev-page/audit.md` F5 | web-feed |
| WEB-R6 | The e2e Previous flow does not assert that `Next page →` is present on the backward first page. | LOW (accepted) | `specs/archived/web-feed-prev-page/audit.md` F7 | web-feed |
| WEB-R7 | On a last page with only First and Previous, `space-between` puts Previous at the right edge. Accepted default; grouping needs a design revision. | LOW (accepted) | `specs/archived/web-feed-prev-page/intent.md` | web-feed |
| WEB-R8 | With a `tag` filter, a Previous page's boundaries can differ from the forward ones (root FA-R2); the web app does not compensate. | LOW (accepted) | `specs/archived/feed-prev-cursor/` (FA-R2) | web-feed |
| WEBCHAT-R10 | Phone swipe gestures verified only with Chromium CDP touch; the OS or browser may take an edge swipe. Human confirmed tap on an iPhone (Brave) only; swipes and Android gesture navigation unconfirmed (O8 open). | MEDIUM (human) | `specs/archived/web-chat-swipe-handle/audit.md` R1 | web-chat |
| WEBCHAT-R11 | Phone tab is 24 by 64, below the old 44 by 44 target (ADR 0056); `touch-action: pan-y` blocks pinch-zoom that starts on the tab or sheet; redundant inline-style read in `ownsHorizontalGesture`. | LOW (accepted) | `specs/archived/web-chat-swipe-handle/audit.md` R2, F5 | web-chat |
| WEB-R9 | The `.pagerLink` CSS change and 11 regenerated style baselines were made after the `web-chat-swipe-handle` audit and are not audit-verified. | LOW | `specs/archived/web-chat-swipe-handle/design/feed.module.css` | web-feed |

## Notes

`web-feed-ui` (Phase 2 spec 02) archived 2026-09-18 in the repo-root harness
and moved here on 2026-09-20, when `apps/web/` got its own harny harness
(`stack: typescript`: eslint + tsc per-turn feedback, `npm test` readiness).
Paths inside the moved spec files that read `specs/...` are relative to this
harness root (`apps/web/`). **It is locally verified only** — no Vercel deploy
has happened and `feed-api`'s CORS allow-list has not been updated (see
`WEB-R1`).
