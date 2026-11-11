# Audit: feed-prev-cursor

Round 1, 2026-11-10. Branch `feat/feed-prev-cursor` at `c9c0c2f` (= `main`), all changes uncommitted.
Reviewed: `src/api/cursor.py`, `src/api/feed.py`, `src/api/handler.py`, `src/contracts/card.py`,
`export_api_schema.py`, `docs/api/feed-api.v1.schema.json`, `apps/web/features/feed/api/types.generated.ts`,
`tests/test_feed_cursor.py`, `tests/test_feed_api_handler.py`, `tests/test_feed_query.py` (full `git diff HEAD`).
The other modified `apps/web` files (feed components, `client.ts`, `load-feed.ts`, e2e and baselines) are the
human's pre-existing work recorded in `tasks.md` § Baseline. None of them mentions `prev_cursor`/`PrevCursor`,
so they are not attributed to this feature.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `handler.py` forward branch: `prev_cursor=None` iff `exclusive_start_key is None` (no cursor, or keyless `{"dir":"next"}`), otherwise always an encoded token. T3 asserts null on page 1 and non-null after it. T4 `[tag]` exercises the keyless start-of-feed path (5 `keyless-next` encodes, probe below). `uv run pytest tests/ -q` -> 849 passed (rerun) |
| AC2 | PASS (offline) | Backward: `Limit=limit+1`, reverse, drop `items[0]` when `len > limit`, `prev_cursor` null only when nothing was dropped and there is no `LastEvaluatedKey`. T3 (10 cards, two `gsi_sk` tie groups straddling the limit=3 boundaries) asserts page k exactly and `prev_cursor is None` iff k = 1 (rerun). The unfiltered start-of-feed decision does not depend on `LastEvaluatedKey`: reading <= `limit` items with `Limit=limit+1` never reaches `Limit`, so real DynamoDB also returns no key. Real-DynamoDB tie order is unverified offline (F5, AC9 L6) |
| AC3 | PASS | Backward `next_cursor` is `encode(last_key)` or `encode(lek)`, and `encode(None)` yields the start-of-feed token, so it is never null. T3 asserts next -> prev -> next returns page k+1. T4 asserts forward re-walk from the head equals the full walk (rerun) |
| AC4 | PASS | T4 `[no-tag]` and `[tag]`: 12 cards, matches at relevance 9/7/5, a 3-card leading and a 4-card trailing non-matching run at limit=2. A probe shows 20 empty forward pages, 6 empty backward pages, 5 keyless-next and 7 keyless-prev cursors exercised. The backward prefix from every page and the forward re-walk are exact, with no duplicates (rerun). Hand-trace of the intent's AC4 example (`[]`, `[c4,c6]`, `[]`, then back `[c4,c6]`, `[]` with `prev_cursor: null`) matches the code |
| AC5 | PASS | `git diff HEAD -- src/api/cursor.py`: for `direction="next"` with a key the payload is the key itself, serialized with the unchanged `sort_keys=True, separators=(",", ":")` and `=` stripping. The existing exact-encoding test is unchanged in the diff. The AC5 example token decodes to `("next", {...})`, and re-encoding it gives the identical string (rerun, ad-hoc `uv run python`) |
| AC6 | PASS | `decode_cursor` accepts only the bare 3-key object, the 3 keys plus `dir:"prev"`, and lone `{"dir":"next"|"prev"}`. Rejected (rerun, ad-hoc): `dir:"sideways"`, `dir:null`, `dir:1`, `dir:"next"` with a key, `{"dir":"prev","extra":"y"}`, `{"dir":"prev","gsi_pk":"X"}`, `{}`. The handler maps `InvalidCursorError` to the existing 400 before `card_table()` is touched. T2 plus the existing `test_handler_rejects_invalid_cursor_without_touching_dynamodb` pass (rerun) |
| AC7 | PASS | One `table.query(**kwargs)` per call in both directions. There is no loop, no second call and no Scan. T3 counts one query per backward request. `cdk synth AiRadarFeedApi`: the policy is still only `dynamodb:Query` on `.../table/ai-radar-cards/index/feed-by-score`. `cdk diff --no-change-set` against the deployed stack in account 626259825216 shows only `FeedApiFunction` `Code.ImageUri` and asset metadata changed, with no IAM or policy difference (rerun). `git status` shows nothing changed under `infra/` (rerun) |
| AC8 | PASS | `FeedResponse.prev_cursor: str \| None = None`. `CARD_SCHEMA_VERSION`, the route and the artifact name are unchanged. `test_committed_schema_artifact_matches_contracts_json_schema` passes, so the artifact equals the model (rerun). `npx vitest run features/feed/api/types.generated.test.ts` (cwd `apps/web`) -> 3 passed, so the TS file equals `generate()` output of the artifact, i.e. it was generated, not hand-edited (rerun). Of the `apps/web` files, only `types.generated.ts` carries this feature's change. Full suite 849 = 837 baseline + 12 new cases, with no regression (rerun) |
| AC9 | N/A (pending) | A human runs it after merge (O8, runbook L1 to L6). Unavailable to the auditor by design. It is the only check of the moto-vs-real `LastEvaluatedKey` gap and of real tie ordering (F5) |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| One `Query` per request on `feed-by-score`, `Key("gsi_pk").eq("CARD")`, no Scan, no second call, no drain | PASS | `feed.py` `query_feed`: a single `table.query`. `IndexName` and `KeyConditionExpression` are unchanged. T3 query count, existing `test_query_feed_issues_exactly_one_query_call` (rerun) |
| No change to `infra/`; `dynamodb:Query` on the index ARN covers `ScanIndexForward=True` | PASS | `git status` is clean under `infra/`. The synth policy is unchanged and the `cdk diff` shows no IAM change (rerun). The live `AccessDeniedException` check is AC9 L5 (pending) |
| Request surface unchanged (`tag`, `limit`, `cursor`) | PASS | The handler reads only those three. Direction lives inside the cursor |
| Forward cursor encoding frozen | PASS | See AC5. The `encode_cursor` forward-with-key branch is `payload = key`, and serialization is unchanged |
| Decode accepts exactly the issued shapes, `gsi_pk == "CARD"` in every keyed shape, 400 before any DynamoDB call | PASS | See AC6. The foreign `gsi_pk` check runs after the `dir` pop, so it applies to backward keys too (T2 `backward-foreign-pk`) |
| Page cursor rule table (binding) | PASS | Line-by-line check below |
| `CardOut` projection hides `gsi_pk`/`gsi_sk`/`embedding` | PASS | `gsi_pk, gsi_sk` were added to `_PROJECTION_EXPRESSION`. `CardOut` has `extra="ignore"` and drops them. `embedding` is still unprojected. Existing `test_returned_card_never_carries_index_keys_or_embedding` passes (rerun) |
| `apps/web`: only `types.generated.ts`, only via the generator; the human's work untouched | PASS | Vitest drift test green (rerun). No other diffed `apps/web` file references the new field |
| Dependencies: `api` group gains nothing, `uv` only | PASS | `pyproject.toml`, `uv.lock` and `apps/web/package*.json` are unchanged (`git status`, rerun) |
| Planes never import each other | PASS | `src/api/*` imports only `api.*` and `contracts.*` |

### Rule table, line by line (`handler.py` L91-121, `feed.py` L79-116)
- **Forward query**: `ScanIndexForward=False` (`backward` is False), `Limit=limit`, `ExclusiveStartKey` only if a key was decoded. A keyless `{"dir":"next"}` decodes to `("next", None)`, so it starts from the top. PASS.
- **Forward `next_cursor`**: `encode_cursor(lek)` or `None`, the same expression as before. PASS.
- **Forward `prev_cursor`**: `None` if there was no key. Otherwise `encode(first_key,"prev")`. Otherwise (empty page) `encode(lek,"prev")`, which with `lek is None` yields `{"dir":"prev"}` (end of feed). PASS. Note: `first_key` is taken from the first *read* item, which can be a malformed item skipped by `CardOut` validation, not the first *shown* card. This is a compliant alternative: the malformed item is never shown, so anchoring backward-exclusive on it neither skips nor repeats a shown card. Building the key cannot fail on a malformed item, because `card_id` is the table hash key and `gsi_pk`/`gsi_sk` are the index keys, which every item on the sparse GSI carries as strings.
- **Backward query**: `ScanIndexForward=True`, `Limit=limit+1`, `ExclusiveStartKey` if keyed. `{"dir":"prev"}` starts at the bottom (end of feed). PASS.
- **Reverse and drop**: `items.reverse()`, then if `len(items) > limit` drop `items[0]` (first in feed order, furthest from the anchor) and set `has_more_before=True`. `len(Items)` is post-filter, so the drop triggers only when more than `limit` items *match*. PASS.
- **Backward `next_cursor`**: `encode(last_key)` (the item nearest the anchor). Otherwise, on an empty page, `encode(lek)`, which with `lek is None` gives `{"dir":"next"}` (start of feed). PASS. Forward from an empty backward page's `lek` (the furthest evaluated item) re-covers the non-matching run and then the anchor's page, with no gap.
- **Backward `prev_cursor`**: `encode(first_key,"prev")` if a card was dropped (the next backward read re-reads the dropped item). Otherwise `encode(lek,"prev")`. Otherwise `None`. PASS.
- **Equal `gsi_sk` across a boundary**: every keyed cursor carries `card_id`, so the `ExclusiveStartKey` is a full index position. T3 passes with both tie groups straddling boundaries under moto, which orders ties by `(gsi_sk, card_id)`. Real DynamoDB tie order is not verifiable offline (F5).
- **moto vs real `LastEvaluatedKey` at exactly `Limit`**: confirmed by experiment (scratch, moto 5.x). A 3-item query with `Limit=3` returns `LastEvaluatedKey: None` in moto, while real DynamoDB returns a key. Impact analysis:
  - Unfiltered backward: the start-of-feed decision rests on `len(items) > limit`, not on `lek`, so it is immune to the gap.
  - Filtered backward that evaluates exactly `limit+1` items at the start of the feed: in real DynamoDB this yields a dangling `prev_cursor`. Following it gives an empty page with `prev_cursor: null`. AC4 explicitly allows that ("a backward page may be short or empty while its `prev_cursor` is non-null"), so it is not a defect.
  - Forward trailing empty page in real DynamoDB: this is pre-existing FA-3 behavior, and its `prev_cursor` (end of feed) correctly returns the last full page.

  None of these cases is covered offline. Only AC9 L3 and L6 can confirm them.

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | T3 `test_prev_cursor_returns_the_previous_page_and_next_cursor_returns_it_back`; T4 `[tag]` (`tests/test_feed_api_handler.py`) | PASS |
| AC2 | T3 | PASS |
| AC3 | T3; T4 | PASS |
| AC4 | T4 `test_backward_walk_yields_the_exact_prefix_and_forward_from_head_the_whole_feed[no-tag,tag]` | PASS |
| AC5 | T1 `test_decode_of_encode_returns_the_same_direction_and_key[forward-key]`; existing `test_encode_cursor_is_valid_urlsafe_base64_of_key_sorted_json`, `test_handler_accepts_a_cursor_produced_by_encode_cursor` (`tests/test_feed_cursor.py`, `tests/test_feed_api_handler.py`) | PASS |
| AC6 | T2 `test_decode_cursor_rejects_near_miss_direction_shapes` (5 cases); existing rejection tests; `test_handler_rejects_invalid_cursor_without_touching_dynamodb` | PASS (one planned case mislabeled, F2) |
| AC7 | T3 query count; existing `test_query_feed_issues_exactly_one_query_call`; `tests/test_infra_feed_api.py` (unchanged, green); auditor `cdk diff` | PASS |
| AC8 | existing `test_committed_schema_artifact_matches_contracts_json_schema`; `apps/web/features/feed/api/types.generated.test.ts` | PASS |
| AC9 | live runbook L1 to L6 | Pending (human, post-merge) |

Red evidence: `tasks.md` records no actual red run, only the planned red commands (F3). The auditor ran one mutation from a scratch pytest plugin, with no tracked file edited. The mutation widened the backward read by one so the page is not trimmed to `limit`, and T3 fails (`1 failed, 2 passed`), so T3 guards the drop rule. The `Limit=limit` (Q1 option B) mutation is undetectable offline by construction, because moto omits the exact-`Limit` key. The plan states this, and AC9 L3 and L6 own it.

Minimality: exactly T1 (4 cases), T2 (5), T3 (1) and T4 (2) = 12 new cases, all in the two files the plan names. `tests/test_feed_query.py` changed only at the `decode_cursor` call site, with no assertion weakened (diff reviewed). No other test was added.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest) | T1, T2 + existing cursor/contract tests | AC5, AC6, AC8 | Yes (none added) | rerun: `uv run pytest tests/ -q` -> 849 passed | PASS | F2 (T2 case label) |
| integration (pytest + moto) | T3, T4 + existing handler/query tests | AC1, AC2, AC3, AC4, AC7 | Yes (existing fixtures only) | rerun: same run | PASS | - |
| synth (CDK assertions) | existing `tests/test_infra_feed_api.py` | AC7 | Yes | rerun (in the suite); plus `cdk synth`/`cdk diff` by the auditor | PASS | - |
| unit (vitest, `apps/web`) | existing `types.generated.test.ts` | AC8 | Yes | rerun: 3 passed | PASS | - |
| live (curl + jq) | runbook L1 to L6 | AC9 | N/A | not run: post-merge, human-only | N/A (pending) | F5 |

## Feedback verification (`harny-feedback`)
- Stack `python`. Mapped commands ruff (lint) and mypy (typecheck) are wired as Stop/SubagentStop hooks in
  `.claude/settings.json`, and `.sdd/feedback/.turns/` was touched at 21:57 today. No durable hook log
  exists, so "fired and heeded" rests on the executor's record (`tasks.md`: "ruff clean; mypy clean";
  reused, not re-run per the auditor role).
- The CI workflow `.github/workflows/harny-feedback.yml` is present, but it has not run on this change:
  nothing is committed or pushed (`gh run list --branch feat/feed-prev-cursor` is empty). Status unavailable (F4).

## Conventions (`harny-standards`, `CLAUDE.md` § Conventions, `docs/architecture-principles.md`)
- Plane boundary: PASS. Lean style (small functions, `FeedPage` dataclass fields with defaults, no new layer): PASS.
- `uv` only, no new dependency: PASS. Context7 rule: the plan records a DynamoDB docs lookup.

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | MEDIUM | intent Scope In ("The README and runbook notes on the new field, and the post-merge live check") | `README.md` is not modified. Neither the new `prev_cursor` field nor the AC9 live check is documented in the README's feed-api / Phase 2 section. `execution-plan.md` and O5 only defer `docs/history.md` and the capability doc | A README note on `prev_cursor` (and the pointer to the L1 to L6 live check) is added, or the plan explicitly defers it with the human's acknowledgement | Open |
| F2 | MEDIUM | AC6; § Validation T2 | T2's case id `keyless-extra-key` actually sends `{"dir":"next", card_id, gsi_pk, gsi_sk, "extra"}`. That is rejected by the "forward cursors carry no direction marker" branch, not the key-set check. The planned case "a keyless cursor with an extra key" (e.g. `{"dir":"prev","extra":"x"}`) is not tested. The code rejects it (auditor ad-hoc check) | T2 includes a true keyless-plus-extra-key payload (the mislabeled case may stay under a correct id) | Open |
| F3 | MEDIUM | `harny-audit` step 5; `tasks.md` O1/O2/O3 Red lines | No recorded red evidence for T1 to T4 or the schema drift. Outcomes are `[x]` with planned commands, not results. `tasks.md` `## Status` ("Awaiting intent approval"), `Working state` ("Outcome: none started", "Next step: the human records approval") and `Checkpoint` are stale and contradict the checked outcomes | `tasks.md` records the observed red/green results per outcome and the status/working-state/checkpoint reflect "O1-O6 done, audit" | Open |
| F4 | LOW | `harny-feedback` | The CI `harny-feedback.yml` and the backend CI (pytest, ruff, mypy, synth, `cdk diff`) have not run on this change, because nothing is pushed. The hook firing has no durable log | The PR's CI runs are green and the `cdk diff` in CI shows no IAM change for `AiRadarFeedApi` (O8 first bullet) | Open |
| F5 | LOW | AC2, AC9; Risks rows 1-2 | The real-DynamoDB GSI tie order and the exact-`Limit` `LastEvaluatedKey` behavior cannot be verified offline (moto returns no key at exactly `Limit`, confirmed by the auditor's experiment). The `limit+1` design makes the unfiltered start-of-feed decision independent of it, but only the live check proves it | AC9 L1 to L6 recorded in `tasks.md` O8, including L3 `B1.prev_cursor == null` and the L6 `limit=1` full walk both ways | Open (pending post-merge) |
| F6 | LOW | § Validation T3 | The T3 comment says "relevance 5 for ids 0-4", but the code uses `relevance=9`. The test is correct, the comment is inaccurate | The comment matches the data | Open |

Notes (not findings):
- The forward `prev_cursor` anchors on the first item *read* rather than the first card *shown* when a
  malformed item leads the page. This is a compliant alternative with the same no-skip/no-repeat guarantee (see the rule table).
- Real DynamoDB, filtered backward walk reaching the start of the feed at exactly `limit+1` evaluated items:
  one trailing empty page with `prev_cursor: null`. AC4 allows this, but the follow-up `apps/web` spec should drain it
  as the plan's consumer note says.
- The intent's current-truth notes (FA-1 wording, FA-3 amendment, stale `ci-cd.md`) are for `harny-sync` at archive time.
- `.claude/worktrees/` (untracked) predates this feature and is outside scope.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-11-10 | APPROVED WITH RESERVATIONS | AC1-AC8 pass offline; AC9 pending (live, human). 849 passed rerun. `cdk diff` shows no IAM change. No blocking finding; F1-F3 MEDIUM, F4-F6 LOW |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The direction-aware cursor, the `limit+1` backward query and the page cursor rules match the
binding table line by line. The forward encoding is byte-identical, the IAM policy is unchanged against the deployed
stack, the generated artifacts are drift-free, and the full suite (849) passes on rerun. The reservations are
documentation, test-labelling and record-keeping gaps, plus the live-only verification of real-DynamoDB behavior.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F1: add the README note on `prev_cursor` and the live check (intent Scope In).
- F2: add the true keyless-plus-extra-key case to T2.
- F3: record the red/green evidence and refresh the stale status sections in `tasks.md`.

**Recommendations** (nice to have):
- F4: confirm the PR CI (feedback, backend, `cdk diff`) is green before merge.
- F5: run AC9 L1 to L6 after the deploy, especially L3 and the L6 `limit=1` walk, and record the output in O8.
- F6: fix the T3 comment.
