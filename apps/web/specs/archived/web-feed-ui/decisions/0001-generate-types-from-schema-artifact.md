# ADR 0001: Generate TypeScript types from the schema artifact, never hand-author them

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-3, Guarantee 13, Guarantee 14
- **Trigger**: (a) explicit choice between named options; (b) constrains future features; (d) accepts a known, deliberately-guarded cost

## Context

`feed-api` (Spec 01) committed `docs/api/feed-api.v1.schema.json` explicitly
so this consumer could generate its types rather than hand-author them. The
brief left the choice open: "generate if a schema exists, otherwise
hand-author and note the risk." Spec 01's own `tasks.md` names drift between
the two specs as "the main risk of splitting API and UI into separate
specs" — a hand-written interface would make parity a review promise instead
of a build failure.

## Decision

`apps/web/scripts/generate-api-types.mjs` calls
`json-schema-to-typescript`'s `compileFromFile()` with
`additionalProperties: false` against the committed schema artifact, writing
`apps/web/features/feed/types.generated.ts`. The generated file is committed
verbatim (so `next build`/Vercel never need the schema file, which sits
outside the Vercel Root Directory), and a test
(`types.generated.test.ts`) regenerates in-memory and fails the build on any
difference — plus a second test asserting the generated field-name sets
equal the artifact's `properties` keys, so the failure names the drifting
field rather than dumping a whole-file diff.

## Alternatives considered

| Option | Why not |
|---|---|
| Hand-author the `CardOut`/`FeedResponse` interfaces | Parity with `feed-api` becomes a review promise, not a build failure — exactly the risk Spec 01's own `tasks.md` flagged as the main cost of splitting API and UI into separate specs. |
| Generate at build time (not committed) | Would require the schema file to be inside the Vercel Root Directory (`apps/web`), forcing an awkward cross-boundary file layout; committing the generated output keeps `apps/web/` self-contained. |
| `additionalProperties` left at its library default (`true`) | Injects a `[k: string]: unknown` index signature into every generated interface, silently making the types accept fields the API never actually returns — defeats the point of generating from a schema at all. |

## Consequences

**Positive**: Any `feed-api` schema change (a field added/removed/renamed)
breaks this suite loudly and immediately, rather than the UI silently
tolerating or misreading a drifted contract. `tags?`, `takeaways?`, and
`next_cursor?` are correctly typed as optional because the schema's
`required` lists are shorter than its `properties` lists (Pydantic
`default_factory`/`= None` fields) — this is intentional fidelity to the
real contract, not a generator bug.

**Accepted costs**: The generated file's exact formatting is whatever the
library emits (per-field named type aliases, not a hand-tuned shape) — never
hand-edited, even for cosmetic reasons. `json-schema-to-typescript` is a
dev-only dependency; if it is ever abandoned upstream, this decision would
need revisiting.

## Follow-ups

If `feed-api` ever bumps its schema to a `v2`, this app's drift test fails
first — that is the intended coupling, not a defect to fix.
