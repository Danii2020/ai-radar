# ADR 0015: The embedding backfill is a local, idempotent one-shot command

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: curation-pipeline
- **Source**: execution-plan.md § Proposed approach (decision: backfill = `DynamoCardStore` lists un-embedded items, `curation/backfill.py` embeds and writes, `run_backfill_embeddings.py` is the CLI)
- **Trigger**: (a) a choice between named options (local command, Lambda or scheduled job, runtime entrypoint); (d) it accepts that the backfill depends on an operator's credentials

## Context
Cards curated before the embed step have no vector, and AC4 requires a backfill that is idempotent and reports `embedded/skipped/failed`. The backfill is a one-time catch-up, not a recurring job.

## Decision
The backfill runs as a local command, `uv run run_backfill_embeddings.py`, using the operator's own AWS credentials. It lists items without a usable vector, embeds them, and writes each by `card_id`. Before it writes, it prints the account id and table name, so a wrong profile is caught early.

## Alternatives considered
| Option | Why not |
|---|---|
| A Lambda or scheduled backfill | Not needed for a one-time catch-up. It would add a role, a grant and an always-on trigger. |
| An entrypoint on the agent runtime | Adds a second job to the runtime's invocation surface for a one-time task. |

## Consequences
**Positive**: no new role grant and no schedule. A re-run is a no-op: the second run reports `embedded=0`.
**Accepted costs**: the backfill needs an operator with credentials for the target account. The printed account id is the only guard against the wrong account.

## Follow-ups
- Run it once after the pending deploy (step 3 in README "Phase 3 — Chatbot").
