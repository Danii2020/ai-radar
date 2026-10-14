# ADR 0009: Brute-force card retrieval over DynamoDB, with a recorded scale ceiling

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: chat-retrieval
- **Source**: execution-plan.md § Proposed approach (decision: scale ceiling, recorded per the intent constraint); intent.md § Constraints (brute force is the deliberate choice)
- **Trigger**: (b) constrains future retrieval work (the revisit thresholds); (d) deliberately accepts a known cost and an unmeasured latency

## Context
Plane B needs top-k retrieval over the curated cards. The budget anchor is $500 in AWS credits, and CLAUDE.md rules out OpenSearch Serverless and the Bedrock knowledge-base default vector backing (about $700/mo). The corpus is small: the curation run caps new cards at 8 per run. The intent required that the spec record the corpus size or latency at which brute force should be revisited, so that the choice is on file rather than accidental.

## Decision
Retrieval is brute-force cosine. `DynamoCardRetriever` pages through a `Query` on the `feed-by-score` index (partition `CARD`), scores the stored vectors in-process by dot product (vectors are normalized), and returns the top `k`. Revisit this at about **2,000 embedded cards**, or when a measured p95 retrieval latency rises above about **1 s**. The first remedy is an in-process TTL cache in the long-lived chat runtime. The second is pgvector or Aurora, per the design doc's §7.

## Alternatives considered
| Option | Why not |
|---|---|
| OpenSearch Serverless, or the Bedrock knowledge-base default vector store | About $700/mo; would exhaust the $500 credit in under a month (CLAUDE.md). |
| pgvector on Aurora now | An always-on database and a new infrastructure surface before the corpus needs one. |
| `Scan` of the table for the corpus | Similar read cost at this size, but a broader IAM grant. A `Query` on the existing index is narrower (AC6). |

## Consequences
**Positive**: roughly $0 extra. No vector database to run. The vectors live in the table that already exists.
**Accepted costs**: every question reads the whole embedded corpus through `Query`. That read cost has not been measured. No retrieval latency has been measured either, so the 1 s trigger is untested until the chat runtime is deployed. The audit ran no live AWS calls.

## Follow-ups
- The chat-agent-runtime spec decides whether the TTL cache lands there.
- Measure p95 retrieval once the chat runtime is deployed, and check it against the trigger.
- Revisit this ADR when either threshold fires.
