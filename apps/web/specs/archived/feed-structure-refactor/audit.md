# Audit: feed-structure-refactor

Round 1 and round 2 (closure), both 2026-10-03. Auditor: sdd-auditor (harny-audit v1.1). Round 2 evidence is under "Round 2 closure evidence" in `## Findings`.
Reviewed: branch `harny-demo`. Base commit `d343830` (pre-refactor). Red tests, e2e suite and baseline are committed in `8f0e8ee`. The executor's work is the uncommitted working tree (staged `git mv` renames, plus modified `app/page.tsx`, `scripts/generate-api-types.mjs` and `tasks.md`, and untracked `features/feed/index.ts`, `api/load-feed-state.ts` and `lib/search-params.ts`). Unrelated uncommitted harny-harness changes under `.claude/`, `.sdd/`, untracked `AGENTS.md`/`CLAUDE.md` and the repo-root `.github/workflows/harny-feedback-apps-web.yml` are outside this feature's ownership and were not judged.

The executor touched no test file and no e2e asset. `git diff HEAD --stat` over `features/feed/conventions.test.ts`, `api/load-feed-state.test.ts`, `lib/search-params.test.ts`, `e2e/`, `playwright.config.ts`, `package.json`, `package-lock.json`, `.gitignore` and `eslint.config.mjs` is empty (rerun). `8f0e8ee` itself changed no source under `features/`, `app/` or `scripts/`, only the 3 new test files (rerun: `git diff --stat d343830 8f0e8ee -- features app scripts`). So the e2e baseline was captured on unmodified source.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `ls features/feed` gives `api components conventions.test.ts index.ts lib`. Sub-folder contents match the AC example exactly. The case `AC1: the feature root holds only …` passes (rerun). |
| AC2 | PASS | `index.ts` holds exactly 3 named re-exports, with no `export *` and no type export. The runtime-keys case passes: `Object.keys` sorted equals `[FeedView, loadFeedState, parseFeedSearchParams]`. The deep-import scan, the self-import scan and the pure-checker cases pass (rerun). The only `features/feed` references outside the feature are `app/page.tsx` → `@/features/feed` and `scripts/generate-api-types.mjs` (`OUT` file path, not an import) (rerun grep). Recorded red with real temporary violating files: tasks.md O2 (reused). |
| AC3 | PASS | No `"use client"` module exists under `app/` or `features/` (rerun grep; the only hit is the guard's own fixture string). Every `api/` import in `components/` and `lib/` uses `import type`: `card-item`, `feed-view`, `tag-filter`, `tags`. The AC3 scan, AC3 guard, T29, T30 and T31 cases pass. T29–T31 are byte-identical to `d343830`, and new cases are only appended (rerun). |
| AC4 | PASS | `lib/search-params.ts` applies the two expressions from the old `page.tsx` verbatim. `search-params.test.ts` (13 tests) covers every AC4 example plus mixed whitespace and a special-character cursor (rerun). The declared return type is `{ tag: string \| undefined; cursor: string \| undefined }`, not `{ tag?: …; cursor?: … }`. It behaves the same: both keys are always present and the AC's examples show `cursor: undefined`. |
| AC5 | PASS | `api/load-feed-state.ts`'s `catch` body is character-identical to the old `page.tsx` block (side-by-side read). The same keys appear in the same order (`event, code, status, tag, has_cursor`), `JSON.stringify` drops undefined keys, and neither the cursor value nor `error.message` is logged. `load-feed-state.test.ts` (10 tests) pins both AC5 example strings exactly, plus the no-leak and never-throws cases (rerun). e2e `stderr/*` baselines show the real server lines did not change (rerun). See the deviation note below. |
| AC6 | PASS | `app/page.tsx` is 11 lines. Its one import is `@/features/feed`, and it does exactly await, parse, `loadFeedState` and render. `grep -nE "try\|catch\|console\|\.\./features" app/page.tsx` prints nothing (rerun). The rendered output matches the baseline through AC7. |
| AC7 | PASS | `npm run test:e2e` (no update flag): **23 passed** (17.5s), covering 17 baseline scenarios, 1 stub-origin check and 5 navigation checks. Baseline aggregate before and after the run is `8ff62845ad7d751adbc5b43ef0be999dc5f0748eabd5d1003d6bebbb36fe8bd3`, over 56 files. `git status --porcelain e2e` and `git diff 8f0e8ee -- e2e` are empty (rerun). The class normalization depends only on the CSS file's basename (`feed-module__<local>`), so the folder move is correctly invisible to it. |
| AC8 | PASS | `git diff -M HEAD` shows all 7 moved tests as renames. `client.test.ts`, `load-feed.test.ts` and `href.test.ts` are 100% renames. `card-item.test.tsx`, `feed-view.test.tsx` and `tags.test.ts` change only `import type` specifiers. `types.generated.test.ts` changes only the script import, `SCHEMA_PATH` and the path comment. No assertion line changed. Per-file counts (Vitest JSON reporter) are client 16, load-feed 4, types.generated 3, card-item 4, feed-view 15, href 5, tags 5 and conventions 3 + 9 new, which gives 55 original tests passing out of 87 total (rerun). LOW note F4 covers the path comment. |
| AC9 | PASS | `npm run generate:types` leaves `features/feed` with no worktree modification, and `types.generated.ts` shows as a pure `R` rename. `features/feed/types.generated.ts` does not exist (rerun). SHA-256 (rerun): `components/feed.module.css` = `fedbe6ba…151f7` and `api/types.generated.ts` = `405dab9e…deb7d`, both equal to `git show d343830:<old path> \| shasum -a 256`. T1–T3 pass from `api/`. The other moved sources differ only in import specifiers. |
| AC10 | PASS | The `package.json` diff since `d343830` adds only `"@playwright/test": "1.63.0"` (devDependencies) and `"test:e2e"`. The lockfile adds only `@playwright/test`, `playwright` and `playwright-core` 1.63.0 (`devOptional`). Lint is 0 errors with 1 pre-existing warning (generated-file `eslint-disable`, now at its new path). Typecheck, `npm test` (10 files, 87 tests; no `*.e2e.ts` collected) and `npm run build` are all green (rerun). `launch-apps.mjs` sets `FEED_API_BASE_URL` explicitly to the `127.0.0.1:4010` stub for the build and for both instances, and clears `.next/cache/fetch-cache`. `reuseExistingServer: false`. Fixture titles render (stub-origin test). Playwright outputs are git-ignored (`test-results/`, `e2e/.tmp/`) and lint-ignored (rerun). The run happened with `.env.local` present. Offline was not forced, but no AWS host is configured anywhere in the run path. |

**Deviation reviewed: `loadFeedState({ tag?: string; cursor?: string })`.** Acceptable and behavior-neutral. AC5 states the call shape `loadFeedState({ tag, cursor })` and the behavior, not a type; the AC5 example "with no tag and no cursor" itself implies both are optional. `loadFeed` already takes `LoadFeedParams` with optional fields (`load-feed.ts:7,22`), so the call passes the same object through. `page.tsx` always supplies both keys. `tsconfig` has no `exactOptionalPropertyTypes`, so `{tag: undefined}` and `{}` type-check and run alike, and `has_cursor` is `cursor !== undefined` in both cases. The red test (committed `8f0e8ee`) calls `loadFeedState({})`, which forced the choice. The executor recorded it in tasks.md O4. Not a finding.

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| No behavior, markup, copy or CSS change; CSS and generated types move byte-identical | PASS | SHA-256 match (rerun). e2e DOM, styles and console baselines unchanged (rerun). The only `.tsx` source edits are import specifiers. |
| All `feed-api` fetches server-side; no `"use client"` import of barrel or `api/` | PASS | AC3 evidence. `client.ts` and `load-feed.ts` are 100% renames. |
| Cursors byte-identical; never parsed, trimmed or logged | PASS | `search-params.ts` passes the cursor through. The no-leak test passes. The e2e "Next page carries next_cursor byte-identical" test passes (rerun). |
| One render state per request; branching stays in `FeedView`; `loadFeedState` only decides ok/error | PASS | `load-feed-state.ts` returns only `ok`/`error`. `feed-view.tsx` changes only its imports. |
| `feed_fetch_failed` line: same keys, order and omission; no message or cursor | PASS | AC5 evidence (character-identical block, exact-string tests, stderr baselines). |
| No `.sort(`/`.reverse(` under `features/` | PASS | grep over non-test sources is empty. T31 passes (rerun). |
| Existing test assertions untouched | PASS | AC8 evidence. |
| Moves via `git mv` (renames visible) | PASS | All 17 moves show as `R`/`RM` in the index (rerun). |
| `@playwright/test` only new package, devDependency; stub `node:http` only | PASS | AC10 evidence. The stub and launcher import only `node:*` modules (read). |
| E2e never contacts AWS; explicit `FEED_API_BASE_URL`; no server reuse | PASS | AC10 evidence. |
| No `NEXT_PUBLIC_`/`execute-api` literal in new files | PASS | grep. T29 passes (rerun). |
| Deployment human-run; the WEB-11 local smoke check is part of done (intent Constraints) | **PENDING** | No deploy was performed. The WEB-11 smoke check against the real `feed-api` has **not** been run, see F1. |

**Consumers and migration:** `app/page.tsx` is the only external consumer and is migrated. Intra-feature imports are relative across sub-folders. `scripts/generate-api-types.mjs` `OUT` is updated. All 7 moved tests run from their new locations. Docs (O7) are deferred to the documentation and `harny-sync` roles, as planned. The `feed.module.css` header comment is untouched (100% rename).

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `features/feed/conventions.test.ts`: "AC1: the feature root holds only …" | PASS |
| AC2 | `features/feed/conventions.test.ts`: export-surface, deep-import, self-import and both "AC2 guard" cases | PASS |
| AC3 | `features/feed/conventions.test.ts`: two "AC3" scans and the "AC3 guard" case; T29–T31 | PASS |
| AC4 | `features/feed/lib/search-params.test.ts` (13) | PASS |
| AC5 | `features/feed/api/load-feed-state.test.ts` (10); e2e `stderr/*` baselines | PASS |
| AC6 | review + grep; `e2e/feed.e2e.ts` | PASS |
| AC7 | `e2e/feed.e2e.ts` (23) against `e2e/__baseline__/**` | PASS |
| AC8 | the 7 moved Vitest files (55 tests) | PASS |
| AC9 | `features/feed/api/types.generated.test.ts` (T1–T3); codegen and SHA commands | PASS |
| AC10 | `e2e/feed.e2e.ts` stub-origin test; the four gates | PASS |
| WEB-11 (binding) | manual smoke against the real `feed-api` | **NOT RUN** (F1) |

Red evidence (reused from tasks.md O2): the new unit files failed at import, AC1 and the barrel-surface case failed on the pre-move tree, and each scan case was shown red with temporary violating files that were then removed. It is plausible, and consistent with the committed red tree at `8f0e8ee`. Every guard's pure checker is additionally exercised green and red on inline sources in the current run, so no test seam is dead.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (Vitest) | 10 files, 87 tests (`features/feed/**/*.test.ts(x)`) | AC1, AC2, AC3, AC4, AC5, AC8, AC9 | Yes: no setup added, `vitest.config.mts` unchanged | rerun: `npm test` 87/87 | PASS | none |
| e2e (Playwright 1.63, Chromium) | `e2e/feed.e2e.ts` (23) | AC6, AC7, AC10 | Yes: `@playwright/test@1.63.0` devDep, `test:e2e`, `playwright.config.ts` (`*.e2e.ts` `testMatch`, `{arg}{ext}` template, `list` reporter, no reuse), `node:http` stub, `fixtures/populated.json`, 2× `next start` (3100/3101), ignore entries. `e2e/stub/launch-apps.mjs` is the implementation of the plan's "one build, two `next start`" step under the `e2e/**` ownership, not unplanned setup. | rerun: `npm run test:e2e` 23/23, no update flag | PASS | none |
| review (AC6) | grep + read of `app/page.tsx` | AC6 | n/a | rerun | PASS | none |
| manual (WEB-11) | none (by design) | WEB-11 binding row | `.env.local` as-is | not run: needs the live `feed-api` and a human browser session; not executed by the executor or the auditor | N/A (pending) | F1 |

No test exists at a tier that § Validation does not name.

## Conventions and feedback
- **harny-standards** (`apps/web/AGENTS.md` § Coding standards, plus WEB-6..8 from `specs/current/web-feed.md`), checked live:
  - WEB-1, WEB-2, WEB-3, WEB-4 (`load-feed.ts` 100% rename) and WEB-5 PASS.
  - WEB-6 PASS: `client.ts` is a 100% rename, so `REVALIDATE_SECONDS` and `AbortSignal` are unchanged.
  - WEB-7 PASS: `tags.ts` changes only an import.
  - WEB-8 PASS: no CSS or `app/globals.css`/`layout.tsx` change.
  - WEB-9 PASS (SHA).
  - Style: colocated tests, small modules, one-line structured server log. PASS.
  - Tests follow `high-value-tests`: no tautologies, and the source scans live only in the existing conventions guard. PASS.
- **harny-feedback**: the per-turn hooks are configured in `.claude/settings.json` (PostToolUse `run-feedback.mjs accumulate`, Stop `run` with eslint + tsc). There is no durable per-turn log (`.sdd/feedback/.turns/` holds only `.gitignore`), so whether the hook fired cannot be shown from artifacts. CI workflow `harny-feedback-web.yml` is present, but the change is uncommitted and unpushed, so no CI run exists against it (`gh run list` returns 404: the workflow is not on the default branch). At the caller's explicit request, lint and typecheck were rerun in the auditor's context, which deviates from harny-feedback's "verify, do not re-run". Result: 0 errors, 1 pre-existing warning (the generated file's `eslint-disable`; baseline-recorded, not a finding). See F3.

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | HIGH | Intent § Constraints ("WEB-11's local smoke check … is still part of the definition of done"); § Validation WEB-11 row; tasks.md O8 | The WEB-11 local smoke check against the real `feed-api` has not been run. The stubbed e2e suite proves the code paths are unchanged. `client.ts`/`load-feed.ts` are byte-identical, so the real-API path's only edit is the relocated try/catch, which unit and e2e tests prove identical. That leaves environmental regression risk low, but the definition of done is not met. **How to run:** from `apps/web/`, keep `.env.local` with the real `FEED_API_BASE_URL`, run `npm run dev`, and open `http://localhost:3000`. Confirm real (non-"E2E fixture") cards render with no browser console errors. Click a promoted tag chip and confirm the URL gains `?tag=` and the list filters. Click "All cards". Click "Next page →" and confirm a second page renders with a `cursor=` URL, then "← First page" returns. The dev terminal should show no `feed_fetch_failed` line. | A human runs the check and records the date, outcome and observations in tasks.md O8. O8 is marked `[x]`, or `[!]` with an explanation if it fails. | Closed (round 2, on human attestation) |
| F2 | MEDIUM | Process gate (`post-specs`); intent.md header | `intent.md` still reads `Approval: Pending`, and tasks.md `## Status` still reads "Awaiting intent approval". The spec gate has no recorded human approver, so the audit trail cannot show the human accepted the ACs, including open question 1 (the three-export surface) and the `@playwright/test` exception. This is not a code defect, so it is MEDIUM ("missing documentation"). It must close before archive. | The human (by name) records `Approval: Approved by <name>, <date>` in intent.md. The answers to open questions 1–4 are recorded. tasks.md Status is updated. | Closed (round 2) |
| F3 | LOW | harny-feedback (audit step 8) | There is no durable evidence that the per-turn feedback hook fired during implementation, and no CI run exists against the change, because it is uncommitted. The auditor's own rerun shows lint and typecheck clean, so this is an evidence gap, not a defect. Separately, the untracked `.github/workflows/harny-feedback-apps-web.yml` appears to duplicate `harny-feedback-web.yml`. It is harness-reinstall state outside this feature, and is noted only so the human reconciles it before committing. | After commit and push, the `harny-feedback-web.yml` run on the change is green, and its log's `N of M command(s) ran` line shows N > 0. | Open (accepted by the human; tracked as WEB-R4) |
| F4 | LOW | AC8 (comments describing paths may change) | `features/feed/api/types.generated.test.ts`: the updated comment reads "apps/web/features/feed -> repo root is five levels up". The level count is right, but the start directory is now `apps/web/features/feed/api`. Cosmetic: the path constants themselves are correct, and T1–T3 pass. | The comment names `apps/web/features/feed/api` (an AC8-permitted path-comment change). Can also be waived. | Closed (round 2) |
| F5 | LOW | harny-audit step 4 (outcome completion) | tasks.md bookkeeping is stale. O1 and O2 are still `[ ]` even though both carry full red/green evidence. O8 is `[ ]` with no note. The "Working state" section still says "Outcome: none started / awaiting human approval". | O1 and O2 are marked `[x]`. O8 is marked `[x]` or `[!]` with the F1 outcome. Working state is refreshed. | Closed (round 2) |

### Round 2 closure evidence (2026-10-03)
The spec is now archived at `specs/archived/feed-structure-refactor/`. Gates rerun this round, with e2e not rerun on the coordinator's instruction:
- `npm run lint`: 0 errors and 1 pre-existing warning.
- `npm run typecheck`: clean (rc 0).
- `npm test`: 10 files, 87/87 pass.

All three are rerun results.
- **F1, closed on the human's attestation.** The human ran the WEB-11 local smoke check manually against the real `feed-api` on 2026-10-03 and reported "the smoke test looks good". This is recorded in `tasks.md` O8, which is `[x]` with that evidence and says the executor did not run it. **The auditor did not run or observe this check**, so its evidence is `unavailable` to the auditor and rests solely on the human's attestation.
- **F2, closed.** `intent.md` line 6 reads `Approval: Approved revision 1 by Daniel Erazo on 2026-10-03` (verified). Approving revision 1 accepts the three-export surface (open question 1). Open question 4 is answered by `decisions/0008-feed-feature-split-by-role-behind-one-entry-point.md`. Open questions 2 and 3 stay as out-of-scope notes; neither blocks this feature. `tasks.md` Status is updated.
- **F3, stays Open (LOW).** The human accepted it, and it is recorded as reservation WEB-R4 in `specs/current/web-feed.md` and `specs/current/_index.md` (verified). The human must resolve the untracked duplicate `.github/workflows/harny-feedback-apps-web.yml` and get a green CI run.
- **F4, closed.** `features/feed/api/types.generated.test.ts:21` now reads `// apps/web/features/feed/api -> repo root is five levels up.` (verified). It is a comment-only change and T1–T3 still pass.
- **F5, closed.** `tasks.md` has O1–O6 and O8 marked `[x]` with evidence. The Status and Working state sections are refreshed. O7 (docs) and O9 (this audit record) remain, as designed (verified).

Notes, not findings:
- The `e2e/.tmp/` directory holds executor scratch files (`agg.txt`, `baseline.sha256`, `manifest.md`). They are git-ignored, by design.
- `app/__golden__/` is still empty and untouched (intent open question 3).
- No `*-E`, `.orig`, `.rej` or `.bak` files exist anywhere in the repo, excluding `node_modules`, `.git`, `.venv`, `cdk.out` and `.next`.
- The pre-existing lint warning only moved path.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-03 | APPROVED WITH RESERVATIONS | Every AC passed on a rerun. 87/87 unit and 23/23 e2e tests passed, the baseline checksum and SHA-256 hashes are unchanged, and the build is green. F1 (WEB-11 smoke not run) must close before merge. F2 must close before archive. |
| 2 | 2026-10-03 | APPROVED WITH RESERVATIONS (final; audit complete) | F1 closed on the human's attestation that the WEB-11 smoke check passed; the auditor did not run it. F2, F4 and F5 verified and closed. F3 (LOW) stays open as WEB-R4, for the human. Rerun this round: lint 0 errors, typecheck clean, 87/87 unit tests. The human signed off: "Approved the audit and mark it complete" (accepted 2026-10-03). |

## Final verdict

APPROVED WITH RESERVATIONS

**Status**: Audit complete. The human signed off and accepted it on 2026-10-03 ("Approved the audit and mark it complete").

**Summary**: The refactor meets all ten acceptance criteria and every binding constraint. Lint, typecheck, 87 unit tests, build, codegen idempotence, SHA-256 of the CSS and generated types, and 23 e2e tests against the untouched baseline (`8ff62845…8bd3`) were all independently rerun. The WEB-11 real-`feed-api` smoke check passed according to the human's attestation; the auditor did not run it. The only reservation left is F3, a CI and workflow housekeeping item outside the feature's code.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F3 / WEB-R4 (LOW, Open, the human's to resolve): reconcile the untracked duplicate `.github/workflows/harny-feedback-apps-web.yml`, then confirm a green `harny-feedback-web.yml` run on the pushed change whose log shows N > 0 commands ran.

**Recommendations** (nice to have):
- Documentation role (O7): AGENTS.md Components tree, README `npm run test:e2e` runbook line, and `specs/current/web-feed.md` path and invariant-3 updates.
