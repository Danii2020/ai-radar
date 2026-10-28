# ADR 0042: Deploy targets come from the changes since the last successful deploy, not from the parent commit

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (change detection, ADR candidate 0042)); § Binding constraints (the deploy base, AC4 and AC5); § Risks (a superseded queued run drops changes)
- **Trigger**: (a) it chooses the last successful deploy commit over the parent commit, a moving git tag and an SSM parameter; (b) every future deploy-relevant path must be mapped to a target, and an unmapped path selects every target

## Context
The deploy workflow runs one deploy at a time, and it never cancels an in-flight deploy (AC4). A newer push can therefore supersede a queued run. If the deploy used the parent commit of the push as its base, a superseded commit's changes would never deploy. A failed run's changes would also be lost.

## Decision
The planner's base is the head commit of the last successful run of the deploy workflow on `main`, read from the GitHub API (`actions: read`). The planner takes the paths changed from that base to `HEAD`, applies a committed path-to-target mapping, and returns the ordered targets. If there is no successful base, or the base is not an ancestor of `HEAD`, the planner selects every target. An unmapped path under a deploy-relevant root also selects every target. Targets are deployed in the pinned dependency order.

## Alternatives considered
| Option | Why not |
|---|---|
| The push's parent commit as the base | A superseded queued commit's changes would be dropped. |
| A moving git tag for the last deploy | It needs `contents: write`. |
| An SSM "last deployed" parameter | It needs an extra write permission from CI. |

## Consequences
**Positive**: no change is lost when a run is superseded or fails, because the next successful run's base still covers it. An unknown deploy-relevant path fails safe. The mapping and the base cases are unit-tested with injected git and GitHub inputs (AC4, AC5). A docs-only merge selects nothing and makes no AWS call.
**Accepted costs**: over-selection costs time. A path added under a deploy-relevant root with no mapping deploys everything until someone adds a mapping. The base depends on the GitHub API and on `actions: read`. The first run has no base, so it deploys everything.

## Follow-ups
- A docs-only merge reports "Nothing to deploy" on the first real merge (tasks O12 g, not yet run).
- None else.
