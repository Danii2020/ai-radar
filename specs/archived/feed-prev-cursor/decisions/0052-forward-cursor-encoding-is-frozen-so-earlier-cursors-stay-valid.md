# ADR 0052: The forward cursor encoding is frozen, so cursors issued earlier stay valid

- **Status**: Accepted
- **Date**: 2026-11-10
- **Feature**: feed-prev-cursor
- **Capability**: feed-api
- **Source**: execution-plan.md § Binding constraints (forward cursor encoding is frozen); § Proposed approach (Decision: old cursors are accepted as forward cursors, not rejected; Decision: suggested token shapes); intent.md § Open questions, Q2
- **Trigger**: (a) it chooses between accepting cursors issued before the change and rejecting them with 400, and between a bare key and a versioned envelope for every cursor; (b) every later change to the cursor must keep the forward token byte-identical or ship its own decision

## Context
Cursors already exist in the wild. `apps/web/app/page.tsx` passes `?cursor=` from the address bar, so bookmarked and shared URLs carry tokens that were issued before backward paging. Rejecting them would break those URLs.

## Decision
For a forward position with a key, `encode_cursor` returns exactly the token it returned before the change: base64url of the compact, key-sorted JSON of `{card_id, gsi_pk, gsi_sk}`, with `=` padding stripped. Such a token decodes as a forward cursor and returns the same page as before. The existing exact-encoding test is kept unchanged, so the rule is enforced by a test.

## Alternatives considered
| Option | Why not |
|---|---|
| Reject cursors issued before the change with 400 | Breaks bookmarked and shared `?cursor=` URLs, and the web app's address-bar flow. |
| A versioned envelope for every cursor, such as `{"v": 2, ...}` | It either rejects old cursors or needs a legacy branch, for no gain. |

## Consequences
**Positive**: no legacy decode branch is needed. The round trip of old tokens is covered by the existing handler test, and the exact-encoding test guards the token bytes.

**Accepted costs**: the forward token format can never change without a new decode branch and its own decision. A future change to the cursor has to justify breaking this rule.

## Follow-ups
None.
