# ADR 0039: Design deliverable revisions live with the feature that makes them

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui-polish
- **Capability**: web-feed
- **Source**: execution-plan.md § Proposed approach 13
- **Trigger**: (c) it diverges from a previously shipped decision (WEB-9 and ADR 0005 named the archived deliverable), and (b) it constrains future features

## Context
`feed.module.css` must stay byte-identical to its design deliverable (WEB-9, ADR 0005), whose only copy is under `specs/archived/web-feed-ui/claude-design-outputs/`. Archives are integrity-checked records and are never edited. A long feed URL overflowed a phone screen and needed one declaration.

## Decision
To change a byte-verbatim CSS file, copy the latest deliverable into `specs/<feature>/design/`, change it there, and copy it over the app file. Archived revisions are never edited. WEB-9's "deliverable" means the latest revision. This feature's revision adds only `overflow-wrap: anywhere;` to `.urlLine` (`specs/archived/web-chat-ui-polish/design/feed.module.css`).

## Alternatives considered
| Option | Why not |
|---|---|
| Edit the archived file | It breaks the archive's integrity record. |
| An app-owned override class | It changes the class lists the DOM baselines capture. |

## Consequences
**Positive**: WEB-9 stays verifiable with `cmp` and the archive stays intact; the 17 feed baselines pass unchanged.
**Accepted costs**: the latest deliverable is now found by following the newest feature's `design/` directory, not one fixed path.

## Follow-ups
None.
