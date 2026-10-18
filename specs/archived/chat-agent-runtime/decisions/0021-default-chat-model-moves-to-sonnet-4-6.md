# ADR 0021: The default chat model moves from Sonnet 4.5 to Sonnet 4.6, and the Sonnet 4.6 end-of-life date is unconfirmed

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: chat-agent
- **Source**: execution-plan.md § Proposed approach (Decision (model default)); § Risks (Sonnet 4.6 rejects the `cachePoint`); intent.md § Outcome, § AC9, § Constraints (Sonnet 4.6 lifecycle) and § Open questions
- **Trigger**: (c) it supersedes the previous default, Sonnet 4.5, which Bedrock reports as `LEGACY`; (d) it accepts an unverified claim, a third-party tracker's retirement estimate of "not sooner than" 2027-02-17 that the spec could not confirm against Anthropic's page

## Context
The Phase 0 chat default was Sonnet 4.5, the `SONNET_MODEL_ID` default in `src/shared/config.py`. Bedrock now reports Sonnet 4.5 as `LEGACY`. Sonnet 4.6 is the chat model the design targeted. The account can call it, and on 2026-10-14 Bedrock reported it `ACTIVE` with no end-of-life date. The request shape the chat sends, a system prompt with a `cachePoint` and a `temperature`, had never been proven against Sonnet 4.6.

## Decision
The `SONNET_MODEL_ID` default becomes `us.anthropic.claude-sonnet-4-6`, the cross-region profile, and its comment is corrected. An environment override still wins, and the model ID stays a config knob, so a later move is an environment change rather than a code change. The Haiku default and the curation graph are unchanged. The AC10 smoke call proved the Sonnet 4.6 request shape on 2026-10-18.

## Alternatives considered
| Option | Why not |
|---|---|
| Keep Sonnet 4.5 as the default | It is `LEGACY` in Bedrock, so it is on a path to failing. |
| Move the chat to Haiku 5.5, as intent revision 2 proposed | Dropped in intent revision 3, before approval, once Sonnet 4.6 was usable in the account. The design targets Sonnet for chat. |
| Hard-code the model ID without a config knob | A model change would then need a code change and a redeploy of the image. |

## Consequences
**Positive**: the chat runs on a supported model, the design's target. The model is still a single config value.
**Accepted costs**: the lifecycle claim is unconfirmed. Anthropic's own retirement date for Sonnet 4.6 may be earlier than the third-party estimate. A `.env` file can still pin the old model locally (the audit's F9), so the runbook prints the model ID before any call.

## Follow-ups
- Re-check Sonnet 4.6's lifecycle on Anthropic's own page before the next model move, and record the result in the chat-agent capability.
