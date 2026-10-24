# ADR 0036: Build AI-Elements-shaped local components, not shadcn/ui or AI Elements

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui-polish
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 1
- **Trigger**: (a) a choice between named viable options

## Context
The chat widget needed markdown, auto-scroll, a branded header and a composer. Vercel AI Elements offers those parts, and the human decided before drafting how to get them. The app uses CSS Modules and has no Tailwind.

## Decision
Write plain React components under `features/chat/components/` that copy AI Elements' names and composition (`Conversation`, `Message`, `MessageResponse`, `Sources`, a loader, `PromptInput`), styled with CSS Modules and the existing tokens.

## Alternatives considered
| Option | Why not |
|---|---|
| shadcn/ui | `shadcn init` rewrites `globals.css`, which breaks WEB-9 and the CSS Modules setup; the app has no Tailwind. |
| Vercel AI Elements | Pulls in `ai`, `@ai-sdk/react`, `streamdown` and Radix for a stream the backend does not send. |
| Keep the monolithic `message-list.tsx` | It does not separate user text from rendered markdown. |

## Consequences
**Positive**: no framework dependency and no change to the token pipeline; a later move to AI Elements would be a rename, not a redesign.
**Accepted costs**: the team owns these components and their accessibility and tests.

## Follow-ups
None.
