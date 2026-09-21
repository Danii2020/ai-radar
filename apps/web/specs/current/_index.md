# Current-State Specifications — apps/web (frontend)

> Current truth for the Next.js frontend. Maintained by `harny-sync`; do not hand-edit.
> Last synced: 2026-09-20 (component split — this index was carved out of the
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
| web-feed | [web-feed.md](./web-feed.md) | [web-feed-ui](../archived/web-feed-ui/) |

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
| server-only fetch / "use client" | web-feed |

## Synchronized Changes

| Change | Archive | Current-State Specification |
|---|---|---|
| web-feed-ui | [specs/archived/web-feed-ui/](../archived/web-feed-ui/) | [web-feed.md](./web-feed.md) |

## Decisions (ADR registry)

ADR numbers are **repo-wide monotonic** across both harness roots (this one and
the repo root's). The next ADR written in either harness is **0008**.

| ADR | Title | Status | Capability | Path |
|---|---|---|---|---|
| 0001 | Generate TypeScript types from the schema artifact, never hand-author them | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md](../archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md) |
| 0002 | All `feed-api` fetching is server-side only | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0002-server-only-fetching.md](../archived/web-feed-ui/decisions/0002-server-only-fetching.md) |
| 0003 | Pagination is URL cursor links, not client-side "load more" | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0003-url-cursor-pagination.md](../archived/web-feed-ui/decisions/0003-url-cursor-pagination.md) |
| 0004 | Drain empty-but-cursored pages, bounded to 5 requests | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md](../archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md) |
| 0005 | Styling is CSS Modules, copied byte-verbatim from hand-authored design deliverables | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md](../archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md) |
| 0006 | Explicit 300s revalidate on the feed fetch; keep the AbortSignal timeout | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md](../archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md) |
| 0007 | Deployment is a human-run step; the automated pipeline stops at local verification | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md](../archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md) |

## Open reservations

> Non-blocking findings accepted at ship time and still open.

| ID | Reservation | Severity | Source | Capability |
|---|---|---|---|---|
| WEB-R1 | Not yet deployed: no Vercel project exists, and `feed-api`'s CORS allow-list has not been updated to a real Vercel origin. Locally verified only, not live. | HIGH (operational, expected — Phase 5 is human-gated by design) | `specs/archived/web-feed-ui/audit.md` | web-feed |
| WEB-R2 | Whether `AbortSignal.timeout` on the feed fetch disables Next's Data Cache was researched but never empirically confirmed live. Accepted as final, not reopened. | LOW (accepted) | `specs/archived/web-feed-ui/audit.md` AD-9/C25 | web-feed |
| WEB-R3 | `conventions.test.ts`'s no-`NEXT_PUBLIC_`/no-`execute-api` guard scans only `features/**`/`app/**`, not `scripts/`/`*.mjs`/`*.mts`/configs — narrower than its own description, no violation exists today. | LOW | `specs/archived/web-feed-ui/audit.md` | web-feed |

## Notes

`web-feed-ui` (Phase 2 spec 02) archived 2026-09-18 in the repo-root harness
and moved here on 2026-09-20, when `apps/web/` got its own harny harness
(`stack: typescript`: eslint + tsc per-turn feedback, `npm test` readiness).
Paths inside the moved spec files that read `specs/...` are relative to this
harness root (`apps/web/`). **It is locally verified only** — no Vercel deploy
has happened and `feed-api`'s CORS allow-list has not been updated (see
`WEB-R1`).
