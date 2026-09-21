# ADR 0007: Deployment is a human-run step; the automated pipeline stops at local verification

- **Status**: Accepted
- **Date**: 2026-09-18
- **Feature**: web-feed-ui
- **Capability**: web-feed
- **Source**: contract.md § AD-10; roadmap.md Phase 5
- **Trigger**: (b) constrains future features; (c) mirrors and continues a precedent from earlier Phase 1 specs

## Context

Shipping this feature for real requires creating a Vercel project (an
external account/service this repo's automation has no credentials for) and
redeploying `feed-api`'s CDK stack with an updated CORS allow-list. Earlier
Phase 1 specs in this repo already established the pattern that
infrastructure-affecting or account-creating actions are human-run, not
agent-run.

## Decision

No agent runs `vercel`, `vercel deploy`, `vercel link`, or `cdk deploy` for
this feature. An executor's definition of done is: production build, lint,
typecheck, and tests green in `apps/web`, plus one local dev-server browser
smoke check against the real, already-deployed `feed-api`.
`roadmap.md`'s Phase 5 is a runbook — written by the executor, for the
human, with exact commands and exact expected output — containing no
checkboxes an executor may tick itself.

## Alternatives considered

| Option | Why not |
|---|---|
| Let an agent run the Vercel deploy autonomously | Requires provisioning Vercel credentials into the automation's reach and would let an agent create externally-visible, billable (even if free-tier) infrastructure and change a security-relevant CORS allow-list without a human in the loop — inconsistent with every earlier infrastructure-affecting decision in this repo. |

## Consequences

**Positive**: A clean, auditable boundary between "code is correct and
locally verified" (agent-verifiable, and independently re-verified twice in
this feature's own audit) and "the world can reach it" (a human decision
made with full visibility into what's being exposed).

**Accepted costs**: The feature is fully implemented, tested, and audited
but genuinely not live — recorded honestly as `WEB-R1` in the `web-feed`
capability doc's open reservations, not glossed over. `R17`/`R18` and every
`M1`–`M10` row in this feature's archived audit remain `PENDING` until a
human actually runs Phase 5.

## Follow-ups

Phase 5 itself (Vercel project creation, `FEED_API_BASE_URL` env var, CORS
redeploy with the real origin, curl verification of both CORS halves,
teardown documentation) is written out in full in `roadmap.md` and README's
runbook section, ready for a human to execute at any time.
