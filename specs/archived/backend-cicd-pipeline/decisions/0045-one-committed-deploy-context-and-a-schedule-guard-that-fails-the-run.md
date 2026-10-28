# ADR 0045: The deploy context is one committed file, and a guard fails the run if the schedule is enabled

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (pinned context and guard, ADR candidate 0045)); § Binding constraints (the deploy context, AC6 and AC15; the schedule guard, SC-1); § Risks (a placeholder origin reaches the feed API; the schedule gets enabled by a deploy)
- **Trigger**: (a) it chooses a committed JSON file read by one wrapper over `infra/cdk.json` and over hand-passed flags; (b) the schedule guard and the origin validation are rules every later deploy must obey; (d) it accepts that a CI deploy of `AiRadarSchedule` turns off a schedule a human enabled outside the context

## Context
Every `cdk` call in CI must receive the same context flags: the account's Lambda concurrency overrides (quota 10), the budget limit (500) and the feed API's CORS origins. A CORS origin passed by hand is reverted by the next CI deploy of `AiRadarFeedApi`, because the stack reads the origins from the context. The schedule must stay `DISABLED` (SC-1), and a deploy must never enable it.

## Decision
The four keys live in `scripts/ci/deploy_context.json`. Every CI `cdk` call goes through the wrapper `python -m scripts.ci.cdk`, which adds exactly those flags and refuses any `-c`. There is no `schedule_*` key. The origin validation accepts only `http://localhost:<port>` or an `https://` URL with a host and no path, and it rejects placeholder-shaped values. It runs before synth. After synth, the schedule guard reads `cdk.out/AiRadarSchedule.template.json` and fails the run unless the `AWS::Scheduler::Schedule` state is `DISABLED`. Humans use the same file for local deploys.

## Alternatives considered
| Option | Why not |
|---|---|
| Put the context in `infra/cdk.json` | The README's `cdk --app "python infra/app.py"` from the repo root does not read it, so humans and CI would diverge silently. |
| Pass the origin by hand | The next CI deploy of `AiRadarFeedApi` reverts it. |
| Commit `https://<project>.vercel.app` as a literal | A placeholder would block every run, and if it passed it would be deployed as a real origin. |

## Consequences
**Positive**: CI and the human's local deploys use one set of flags. A placeholder origin fails the PR before it can deploy. An enabled schedule fails the run before any deploy. The guard and the origin validation are offline-tested. The Vercel origin is added by a one-line PR, and the PR diff shows the CORS change (AC2).
**Accepted costs**: a CI deploy of `AiRadarSchedule` also turns off a schedule a human enabled outside the context. That is intended until the context source says otherwise. Until the Vercel project exists, the committed origin is only `http://localhost:3000`.

## Follow-ups
- Add the Vercel origin by PR when the project exists, then check the preflight (tasks O12 i, not yet run).
