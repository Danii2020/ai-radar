# ADR 0058: Amend the dependency rule for `@vercel/analytics`, rendered only on Vercel

- **Status**: Accepted
- **Date**: 2026-11-18
- **Feature**: web-chat-response-cache
- **Capability**: web-chat
- **Source**: execution-plan.md § Binding constraints and § Proposed approach (the `VERCEL` gate); intent AC14
- **Trigger**: (b) constrains future features (the sanctioned dependency list); (a) a choice between named options

## Context
`AGENTS.md` allows only a short, exactly pinned list of runtime dependencies beyond the base toolchain, and a further one needs its own ADR (as ADR 0037 did for `react-markdown` and `use-stick-to-bottom`). The human asked for Vercel Web Analytics. Its `Analytics` component loads a script from `/_vercel/insights/script.js` in production mode, and in development mode from `cdn.vercel-insights.com`. The e2e tier runs `next start` (production mode), asserts an empty console and only local requests, and must stay offline.

## Decision
`@vercel/analytics` is added as a runtime dependency pinned exactly (`2.0.1`) and joins the sanctioned list in `AGENTS.md`. It is imported only by `app/layout.tsx`, through `@vercel/analytics/next`, never from `features/` (guarded by `conventions.test.ts`), and rendered as `{process.env.VERCEL ? <Analytics /> : null}`, so local, unit and e2e runs never load a Vercel script. Page views only: no custom event, no `beforeSend` data, nothing from the chat. Enabling Web Analytics for the project in the Vercel dashboard is a human step.

## Alternatives considered
| Option | Why not |
|---|---|
| The `mode` prop | Development mode loads a script from an external CDN, which breaks the offline rule, and production mode 404s locally and dirties the console the e2e specs assert on. |
| A `NEXT_PUBLIC_` flag | WEB-1 forbids `NEXT_PUBLIC_` variables. |
| Always render it | Every e2e "clean console" check would fail. |
| Server-side or custom analytics | Out of scope; the hosted dashboard is what was asked for. |

## Consequences
**Positive**: page views appear in the Vercel dashboard with no cookie and no change to any response or UI state; the offline e2e tier is unaffected.
**Accepted costs**: one more runtime dependency (with optional peers for other frameworks, none installed). The gate relies on Vercel setting `VERCEL` at build and runtime; if it stops, analytics silently stop, which the post-deploy check would show as a missing dashboard entry.

## Follow-ups
Human steps: enable Web Analytics in the dashboard and confirm the first page view after deploy.
