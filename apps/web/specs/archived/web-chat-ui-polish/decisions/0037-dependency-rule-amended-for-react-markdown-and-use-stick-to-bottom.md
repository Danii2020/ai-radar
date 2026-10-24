# ADR 0037: Amend the dependency rule for `react-markdown` and `use-stick-to-bottom`

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui-polish
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 3
- **Trigger**: (a) a choice between named options, and (b) it constrains future features (a new dependency needs its own ADR)

## Context
`AGENTS.md` sanctioned only `@playwright/test` and `aws4fetch` beyond the base toolchain. The polish needs markdown rendering and stick-to-bottom scrolling.

## Decision
`AGENTS.md` now also sanctions `react-markdown` (runtime, exact pin, rendering assistant answers only, never with a raw-HTML plugin) and `use-stick-to-bottom` (runtime, exact pin, the conversation scroll only). Both are pinned exactly and checked for age with `npm view`. A further dependency needs its own ADR. `remark-gfm` is rejected by human decision: tables cannot fit a 375 px sheet.

## Alternatives considered
| Option | Why not |
|---|---|
| A hand-written scroll hook (`scrollIntoView` plus a scroll listener) | It would have to rebuild handling of content that grows after layout, user versus programmatic scroll, and the escape state, and is the usual source of "yanks the reader" bugs. `use-stick-to-bottom` has no dependencies, and AI Elements' `Conversation` is built on it. |
| `remark-gfm` | Tables do not fit a phone sheet; a model-written table shows as plain text. |

## Consequences
**Positive**: tested behaviour for the two hardest parts, with a small, closed dependency list.
**Accepted costs**: two more runtime dependencies and extra client JavaScript in the chat chunk; `vitest.setup.ts` needs a no-op `ResizeObserver`.

## Follow-ups
None.
