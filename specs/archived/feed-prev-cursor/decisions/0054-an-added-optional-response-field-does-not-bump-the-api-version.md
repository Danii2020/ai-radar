# ADR 0054: An added optional response field does not bump the API version

- **Status**: Accepted
- **Date**: 2026-11-10
- **Feature**: feed-prev-cursor
- **Capability**: feed-api
- **Source**: execution-plan.md § Proposed approach (Decision: `prev_cursor: str | None = None` on `FeedResponse`, schema stays `v1`); § Consumers and migration (the docstrings in this change); intent.md § AC8 and § Current-truth notes (the docstrings that call any change "a BREAKING API change")
- **Trigger**: (b) it sets the rule every later change to `CardOut` or `FeedResponse` must follow; (c) it diverges from the rule recorded in the `export_api_schema.py` and `src/contracts/card.py` docstrings, which called any change to these models a breaking change that needs a version bump

## Context
The feed API is `v1` and has consumers outside this repo's Python code. The `apps/web` client reads named fields only. The Pydantic model ignores unknown fields, and the generated TypeScript type gains an optional property. The earlier docstrings said any change to `CardOut` or `FeedResponse` was breaking, which would have forced a `v2` for an added field.

## Decision
A removal, rename or type change of a `CardOut` or `FeedResponse` field bumps `CARD_SCHEMA_VERSION`, the route and the artifact name. An added optional, nullable response field does not. `prev_cursor` is added as `str | None = None`, and `CARD_SCHEMA_VERSION` stays `"v1"`. The docstrings in `src/contracts/card.py` and `export_api_schema.py` state this rule.

## Alternatives considered
| Option | Why not |
|---|---|
| Bump to `v2` for the new field | Renames the route and the artifact for no client gain, and the frontend would need a change it does not need. |
| Keep the earlier docstring rule | It would require a version bump for an additive, optional field. |

## Consequences
**Positive**: existing `v1` clients keep working, and the route and artifact names do not change. The schema-drift test still guards the committed artifact against the model.

**Accepted costs**: this rule holds only if clients ignore unknown response fields. `apps/web` does. The project does not know of other consumers, and a strict parser outside this repo would break on `prev_cursor`.

## Follow-ups
None.
