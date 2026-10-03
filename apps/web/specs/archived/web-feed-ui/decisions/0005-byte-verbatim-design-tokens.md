# ADR 0005: Styling is CSS Modules, copied byte-verbatim from hand-authored design deliverables

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-7 (revised 2026-09-18), AD-12, AD-13; Data Models field-rendering table
- **Trigger**: (a) explicit choice between options; (c) supersedes an earlier plan and, separately, a post-audit implementation choice; (d) accepts a known cost (duplicated literal across a language boundary)

## Context

The original plan (before human design deliverables existed) was to
hand-port `src/shared/cards.py`'s `_TYPE_COLOR` map into CSS custom
properties. Partway through the spec's life, the human supplied two
hand-authored files — `tokens.css` (palette, spacing/radius/type scales,
per-type accents) and `feed.module.css` (concrete class names for every
component, keyed to this contract's `data-testid`s) — which superseded that
plan with pinned values and names.

Separately, after the first implementation pass, the auditor found a real
conflict: the design mockup and `feed.module.css`'s unused `.urlLine` class
both called for a visible URL line under each card's title, matching this
contract's own Data Models field-rendering table ("`url` → the heading's
`href` + a visible link line") — but the executor had rendered only the
title anchor, because a human-approved red test (`card-item.test.tsx`'s
T28) asserted exactly one link. Test and design/contract text disagreed with
each other.

## Decision

`app/globals.css` and `features/feed/feed.module.css` are exact,
byte-verbatim copies of `specs/archived/web-feed-ui/claude-design-outputs/
tokens.css` and `feed.module.css` — no hand-edited color, spacing, or radius
value may exist outside those two files' custom properties, and the per-type
card accent is applied purely via a `data-type` CSS attribute selector
(`.card[data-type="paper"]` etc.), never a TypeScript colour-lookup helper.

When the URL-line conflict surfaced, the human resolved it by **rendering
the line** (adding a second anchor using the already-provisioned `.urlLine`
class) and **amending the test** (T27/T28 now expect 2 links, not 1) —
rather than editing the contract's field-rendering table down to match the
narrower implementation, and rather than deleting `.urlLine` from the
verbatim CSS copy (which would have violated this same decision from the
other direction).

## Alternatives considered

| Option | Why not |
|---|---|
| Hand-port `_TYPE_COLOR` as a TS colour map (original plan) | Superseded once real design deliverables existed with pinned values and names — re-deriving colours by hand risked drifting from what the human actually designed. |
| Resolve the URL-line conflict by amending the contract/mockup instead of rendering the line | Would have silently dropped a design element the human explicitly authored CSS for (`.urlLine`, the only unused class in the file) and explicitly drew in the mockup PDF — the test was the artifact that was wrong, not the design. |
| Resolve it by deleting the unused `.urlLine` class from the "verbatim" CSS copy | Directly violates this same ADR's byte-verbatim rule — the CSS files are never hand-edited, even to remove something inconvenient. |

## Consequences

**Positive**: Design changes have one clear point of entry (re-copy the
source file), and there is no chance of an executor inventing a colour/
spacing value that quietly diverges from what a human designer actually
specified. The per-type accent is CSS-only, so an unrecognised `card.type`
simply matches no selector and falls back to `.card`'s own
`--accent-neutral` — no TypeScript code path can throw on an unknown type.

**Accepted costs**: The five-color `_TYPE_COLOR` mapping now exists in two
places across a language boundary (`src/shared/cards.py`'s Python constant,
and `tokens.css`'s CSS custom properties) with no automated drift test
between them — unlike ADR 0001's generated-types guarantee, this drift is
purely cosmetic (an unknown type falls back to neutral, never a crash), so
it is accepted and called out rather than test-guarded.

## Follow-ups

`tokens.css`'s `[data-theme="dark"]`/`[data-theme="light"]` override
selectors are authored but deliberately unused in this phase (see the
separate dark-mode-scope decision) — a future manual theme toggle is
additive to them, not a rewrite.
