# Current-State Specifications

> Current truth for this repo. Maintained by `harny-sync`; do not hand-edit.
> Last synced: 2026-09-18 by harny-sync (archive mode: 1 feature archived
> [web-feed-ui], 1 capability doc created [web-feed], index regenerated —
> see Notes)

## Capabilities

| Capability | Current-State Specification | Incorporated Changes |
|---|---|---|
| curation-pipeline | [curation-pipeline.md](./curation-pipeline.md) | [curation-graph](../archived/curation-graph/), [tavily-discovery](../archived/tavily-discovery/) |
| card-persistence | [card-persistence.md](./card-persistence.md) | [dynamodb-card-store](../archived/dynamodb-card-store/) |
| runtime-deployment | [runtime-deployment.md](./runtime-deployment.md) | [runtime-packaging](../archived/runtime-packaging/), [async-invocation-ack](../archived/async-invocation-ack/) |
| scheduling | [scheduling.md](./scheduling.md) | [eventbridge-schedule](../archived/eventbridge-schedule/) |
| observability | [observability.md](./observability.md) | [run-observability](../archived/run-observability/) |
| config-loading | [config-loading.md](./config-loading.md) | [pydantic-settings-config](../archived/pydantic-settings-config/), [rename-spike-to-shared](../archived/rename-spike-to-shared/) |
| feed-api | [feed-api.md](./feed-api.md) | [feed-api](../archived/feed-api/) |
| web-feed | [web-feed.md](./web-feed.md) | [web-feed-ui](../archived/web-feed-ui/) |

## Keyword lookup

> If your question mentions a term on the left, read the capability on the right first.

| Term | Capability |
|---|---|
| StateGraph / LangGraph | curation-pipeline |
| discover / dedup / summarize / rank / persist | curation-pipeline |
| Discoverer / CompositeDiscoverer | curation-pipeline |
| Tavily discovery | curation-pipeline |
| RSS feeds | curation-pipeline |
| url_hash / dedup key | curation-pipeline, card-persistence |
| CardStore Protocol | card-persistence |
| DynamoCardStore | card-persistence |
| upsert idempotency | card-persistence |
| feed-by-score GSI | card-persistence, feed-api |
| embedding attribute | card-persistence |
| card_id | card-persistence |
| RemovalPolicy.RETAIN | card-persistence |
| AgentCore Runtime | runtime-deployment |
| BedrockAgentCoreApp / runtime_app.py | runtime-deployment |
| Secrets Manager (Tavily key) | runtime-deployment |
| execution role / least privilege | runtime-deployment, scheduling |
| async handler / immediate ack | runtime-deployment |
| single-flight / already_running | runtime-deployment |
| run_id | runtime-deployment, observability |
| EventBridge Scheduler | scheduling |
| Universal target | scheduling |
| dead-letter queue / DLQ | scheduling |
| schedule_enabled / cron | scheduling |
| TargetErrorCount | scheduling |
| double-fire | scheduling |
| RunSummary | observability |
| EMF / CloudWatch custom metrics | observability |
| AiRadarBudget | observability |
| curation_run_complete | runtime-deployment, observability |
| curation_run_metrics | observability |
| estimated_cost_usd | observability |
| pydantic-settings | config-loading |
| AI_RADAR_* / SPIKE_* env keys | config-loading |
| ValidationError (config) | config-loading |
| CURATION_EMIT_METRICS | config-loading, observability |
| .env loading | config-loading |
| shared/ package | config-loading |
| GET /v1/cards | feed-api |
| cursor / next_cursor pagination | feed-api, web-feed |
| CORS (feed-api) | feed-api |
| CardOut / FeedResponse | feed-api |
| tag filter | feed-api, web-feed |
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
| curation-graph | [specs/archived/curation-graph/](../archived/curation-graph/) | [curation-pipeline.md](./curation-pipeline.md) |
| tavily-discovery | [specs/archived/tavily-discovery/](../archived/tavily-discovery/) | [curation-pipeline.md](./curation-pipeline.md) |
| dynamodb-card-store | [specs/archived/dynamodb-card-store/](../archived/dynamodb-card-store/) | [card-persistence.md](./card-persistence.md) |
| runtime-packaging | [specs/archived/runtime-packaging/](../archived/runtime-packaging/) | [runtime-deployment.md](./runtime-deployment.md) |
| eventbridge-schedule | [specs/archived/eventbridge-schedule/](../archived/eventbridge-schedule/) | [scheduling.md](./scheduling.md) |
| async-invocation-ack | [specs/archived/async-invocation-ack/](../archived/async-invocation-ack/) | [runtime-deployment.md](./runtime-deployment.md) |
| run-observability | [specs/archived/run-observability/](../archived/run-observability/) | [observability.md](./observability.md) |
| rename-spike-to-shared | [specs/archived/rename-spike-to-shared/](../archived/rename-spike-to-shared/) | [config-loading.md](./config-loading.md) |
| pydantic-settings-config | [specs/archived/pydantic-settings-config/](../archived/pydantic-settings-config/) | [config-loading.md](./config-loading.md) |
| feed-api | [specs/archived/feed-api/](../archived/feed-api/) | [feed-api.md](./feed-api.md) |
| web-feed-ui | [specs/archived/web-feed-ui/](../archived/web-feed-ui/) | [web-feed.md](./web-feed.md) |

## Decisions (ADR registry)

| ADR | Title | Status | Capability | Path |
|---|---|---|---|---|
| 0001 | Generate TypeScript types from the schema artifact, never hand-author them | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md](../archived/web-feed-ui/decisions/0001-generate-types-from-schema-artifact.md) |
| 0002 | All `feed-api` fetching is server-side only | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0002-server-only-fetching.md](../archived/web-feed-ui/decisions/0002-server-only-fetching.md) |
| 0003 | Pagination is URL cursor links, not client-side "load more" | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0003-url-cursor-pagination.md](../archived/web-feed-ui/decisions/0003-url-cursor-pagination.md) |
| 0004 | Drain empty-but-cursored pages, bounded to 5 requests | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md](../archived/web-feed-ui/decisions/0004-bounded-empty-page-drain.md) |
| 0005 | Styling is CSS Modules, copied byte-verbatim from hand-authored design deliverables | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md](../archived/web-feed-ui/decisions/0005-byte-verbatim-design-tokens.md) |
| 0006 | Explicit 300s revalidate on the feed fetch; keep the AbortSignal timeout | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md](../archived/web-feed-ui/decisions/0006-explicit-revalidate-and-abort-signal.md) |
| 0007 | Deployment is a human-run step; the automated pipeline stops at local verification | Accepted | web-feed | [specs/archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md](../archived/web-feed-ui/decisions/0007-deployment-is-a-human-step.md) |

All 10 features archived in the 2026-09-17 bootstrap pass shipped before
`harny-adr` existed in this project; per that skill's own no-backfill
guardrail, none get retroactive ADRs. `web-feed-ui` (archived 2026-09-18) is
the first feature to register real ADRs here — 7 of its 13 named
architecture decisions were promoted (AD-3, AD-4, AD-5, AD-6, AD-7, AD-9,
AD-10 by contract.md's own numbering); AD-1, AD-2, AD-8, AD-11, AD-12, and
AD-13 were judged lower-impact/narrower-scope and were not promoted (see
`specs/archived/web-feed-ui/` for their full text in the original contract).

## Open reservations

> Non-blocking findings accepted at ship time and still open.

| ID | Reservation | Severity | Source | Capability |
|---|---|---|---|---|
| ES-1 | The prescribed double-fire dedup drill has never been run as its own test. | MEDIUM | `specs/archived/eventbridge-schedule/audit.md` | scheduling |
| ES-2 | The daily cadence has never run unattended — schedule stays `DISABLED`. | MEDIUM (operational, deliberate) | `specs/archived/eventbridge-schedule/audit.md` | scheduling |
| RO-1 | `CURATION_EMIT_METRICS=false` kill switch never exercised live, offline-tested only. | LOW | `specs/archived/run-observability/audit.md` | observability |
| RO-2 | No unattended/scheduled run has ever produced observability records — depends on ES-2. | MEDIUM (operational) | `specs/archived/run-observability/audit.md` | observability |
| FA-R1 | Deployed feed-api Lambda's `ReservedConcurrentExecutions` is unreserved (`null`), not the contract's intended `5`, bridged by an account-quota workaround. | LOW (operational) | `specs/archived/feed-api/audit.md` AD-7 | feed-api |
| WEB-R1 | Not yet deployed: no Vercel project exists, and `feed-api`'s CORS allow-list has not been updated to a real Vercel origin. Locally verified only, not live. | HIGH (operational, expected — Phase 5 is human-gated by design) | `specs/archived/web-feed-ui/audit.md` | web-feed |
| WEB-R2 | Whether `AbortSignal.timeout` on the feed fetch disables Next's Data Cache was researched but never empirically confirmed live. Accepted as final, not reopened. | LOW (accepted) | `specs/archived/web-feed-ui/audit.md` AD-9/C25 | web-feed |
| WEB-R3 | `conventions.test.ts`'s no-`NEXT_PUBLIC_`/no-`execute-api` guard scans only `features/**`/`app/**`, not `scripts/`/`*.mjs`/`*.mts`/configs — narrower than its own description, no violation exists today. | LOW | `specs/archived/web-feed-ui/audit.md` | web-feed |

## Notes

This index was bootstrapped empty on 2026-09-17 (no `specs/current`/
`specs/archived` split existed yet for this project) and populated for real
in the same session once the human resolved the one blocking precondition:
none of the 10 already-shipped features carried a `Shipped:` header. All 10
were then stamped (using each feature's audit sign-off date, not the
bootstrap date) and archived via the normal `harny-document` post-audit
path — see `CHANGELOG.md` for the full per-feature ship history and
`README.md` for live-deploy/verification evidence.

`web-feed-ui` (Phase 2 spec 02, the Next.js frontend) archived 2026-09-18
after passing its full TDD → implement → audit pipeline, a human-approved
fix-up pass resolving all 4 post-audit reservations (a `.env.example`
gitignore bug, a missing design-pinned URL line, an explicit AD-9
acceptance, and Next 16's stray `AGENTS.md`/`CLAUDE.md` auto-scaffold), and
a human running the app locally and confirming it. This created the new
`web-feed` capability doc — it is a genuinely new capability, not a merge
into `feed-api`, because it's a separate runtime/language boundary with its
own toolchain and its own generated-types drift guarantee. **It is locally
verified only** — no Vercel deploy has happened and `feed-api`'s CORS
allow-list has not been updated (see `WEB-R1` above); Phase 5 of
`roadmap.md` remains a human-run runbook.

`rename-spike-to-shared` had one additional blocker beyond the missing
stamp: its audit's Close-out checklist had an open item ("Human confirms
Tasks H1-H3 done"), since its migration includes untracked/gitignored local
state (`.env`, the JSON dedup cache directory) that only a human can move.
The human live-verified all three tasks on 2026-09-17 (see
`specs/archived/rename-spike-to-shared/audit.md`'s Close-out checklist for
the exact verification output) before this feature was archived — which is
also why its `Shipped:` date (2026-09-17) is later than its code-merge/audit
date (2026-08-17): the spec's own contract treats full close-out, not code
merge, as "shipped."

No ADRs were written for any of the 10 features in this pass — `harny-adr`
did not exist in this project when any of them were approved, and that
skill's own guardrail forbids reconstructing rationale retroactively for
already-shipped work. ADRs apply only to features archived from here
forward.
