# Tasks: feed-structure-refactor

## Status
Awaiting intent approval

## Baseline
- Base commit: d343830 (on branch `harny-demo`; the working tree has unrelated, uncommitted harny harness changes under `.claude/` and `.sdd/`)
- Branch: harny-demo
- Interpreter: Node v24.16.0, npm 11.13.0
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: `npm test` (Vitest), `npm run lint` (ESLint), `npm run typecheck` (`tsc --noEmit`), `npm run build` (`next build`). After O1 there is also `npm run test:e2e` (Playwright).
- Pre-existing failures: none. `npm test` gives 8 files and 55 tests, all passing (2026-10-03). `npm run typecheck` is clean. `npm run lint` reports 0 errors and 1 pre-existing warning: an unused `eslint-disable` in `features/feed/types.generated.ts`, which is generated and must not be edited.
- Pre-move SHA-256 values:
  - `features/feed/feed.module.css`: `fedbe6ba59638c4277e972358b35bfb9dc6a0e749479731fbb60925317d151f7`
  - `features/feed/types.generated.ts`: `405dab9ee7ad478b73098870f03f76b2c7e39f3eba1f2a9fe7bcde2d0a1deb7d`

## Outcomes
- [ ] **O1** (AC7, AC10): The Playwright tooling and the characterization baseline are captured on the unmodified tree, before any refactor edit.
  - Steps:
    1. Add `@playwright/test@1.63.0` as a devDependency. This is the sanctioned exception.
    2. Add the `test:e2e` script, `playwright.config.ts`, the stub and the fixtures, `e2e/feed.e2e.ts`, and the `.gitignore` and ESLint ignore entries.
    3. Run the suite once to write `e2e/__baseline__/**`.
    4. Record the SHA-256 of every baseline file below.
  - Tests: `e2e/feed.e2e.ts` (23 tests: 17 baseline scenarios, 1 stub-origin check, 5 navigation), `e2e/stub/feed-api-stub.mjs`, `e2e/stub/launch-apps.mjs`, `e2e/fixtures/populated.json`, `playwright.config.ts`
  - Red: not applicable (characterization). First run on the unmodified tree (git status of `features/` and `app/` clean) with `--update-snapshots=missing`: the 17 scenarios "failed" only with "A snapshot doesn't exist ... writing actual" and wrote the baseline; 6 non-snapshot tests passed. A second `--update-snapshots=missing` run (after restricting stderr lines by has_cursor) wrote only the 5 stderr files.
  - Green: `npm run test:e2e` run twice with no update flag: 23 passed (15.1s, 16.3s), then 23 passed (14.9s, 14.9s). Each run does one `next build`, starts the stub (:4010) and two `next start` (populated :3100, empty :3101) with FEED_API_BASE_URL set explicitly, `reuseExistingServer: false`, fetch cache cleared by the launcher. `npm test` is unaffected (Vitest collects no `*.e2e.ts`).
  - Baseline checksums (56 files; SHA-256 of `e2e/__baseline__/` relative paths). Aggregate: `cd e2e/__baseline__ && find . -type f | sort | xargs shasum -a 256 | shasum -a 256` = `8ff62845ad7d751adbc5b43ef0be999dc5f0748eabd5d1003d6bebbb36fe8bd3`
    - `console/drain-finds-late-page.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/edge-empty-cursor.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/edge-repeated-tag.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/edge-whitespace-tag.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/empty-first-page.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/error-http-with-cursor.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/error-http.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/error-malformed.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/error-network-with-cursor.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/error-network.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/filtered-empty-drained.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/filtered-empty-no-cards-tagged.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/ok-first-page.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/ok-last-page.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/tag-not-promoted.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/tag-promoted.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `console/tag-untrimmed.json` `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
    - `dom/drain-finds-late-page.html` `58b83307331126e246ea230145eb85de7892d81defb4375ffc08e6c38664dc50`
    - `dom/edge-empty-cursor.html` `e2a437bf16f930ae048ff6becb7ab20817d87d3abcb49cb121842431725fb784`
    - `dom/edge-repeated-tag.html` `e2a437bf16f930ae048ff6becb7ab20817d87d3abcb49cb121842431725fb784`
    - `dom/edge-whitespace-tag.html` `e2a437bf16f930ae048ff6becb7ab20817d87d3abcb49cb121842431725fb784`
    - `dom/empty-first-page.html` `37d3c968ae79daa20798fde20121f0be3f612855813612eef35e752c6d8ebd86`
    - `dom/error-http-with-cursor.html` `1e96bba189651f25022dfbe8930d54c249dac1918f8c5e62b43c735edbc680ed`
    - `dom/error-http.html` `83ea15ca76e95a9a4c8b8f8e2556d4e5dc1d79f200babcdfb0fb5d9c3ff6e899`
    - `dom/error-malformed.html` `911ac8df13bffe3af99fdaf65d43d73f01fcf89bda7823996e96190fd85d1c7a`
    - `dom/error-network-with-cursor.html` `27a83ade9b9224850343b4fffa27c94ae8b141000f24e171aa7c04c91daabe7b`
    - `dom/error-network.html` `3349273061ddccd2638a25d410b4a947baa766db01d9527872ebbc60e6fe9e5b`
    - `dom/filtered-empty-drained.html` `752225b499ae27f84dac6b357a26833337bd8890ada7174d044bd58888d61dce`
    - `dom/filtered-empty-no-cards-tagged.html` `80cb9609c479905bd5962a0bbadfa59c211c9750f56ad0417037ff6a0e3eaa55`
    - `dom/ok-first-page.html` `e2a437bf16f930ae048ff6becb7ab20817d87d3abcb49cb121842431725fb784`
    - `dom/ok-last-page.html` `3a302df0543d3b248320ee669d592e2cfbc1daacfb021cc2b867dea88af82e96`
    - `dom/tag-not-promoted.html` `abea6a2b61e7e92da812c8d5d73fb840286b91a5b2c0da508e3a19545b512e30`
    - `dom/tag-promoted.html` `6d271f33fea10ef2fb054036a8c463bec563eea307f4e3f790c8ee8ee23d259d`
    - `dom/tag-untrimmed.html` `8651f6ea135a314ef9a457c46fc4c7247e1436e8a7aecad6dacb91ba22ffc812`
    - `stderr/error-http-with-cursor.txt` `46c998951334f5b73adeccf00c20ba7fef5327dfb699b3f1f7269621e072c6c3`
    - `stderr/error-http.txt` `904f3d59a45251061f782bbbd521c925d178d22b6b02541601a5524a7a100b75`
    - `stderr/error-malformed.txt` `bdd100f82cd6e41fe0ebfe73d73b82c759fe4f29ed879057c837a8962d8df586`
    - `stderr/error-network-with-cursor.txt` `8f06aea3586b93df5c406a9230bc1102d91d0d2aa46e8524e808f660e4750f3e`
    - `stderr/error-network.txt` `143b534b1a3a975d4da14290159cc45cc826f6b858810d68cee1a18abb011ece`
    - `styles/drain-finds-late-page.json` `5f2b8290082ec6fe1a7eb3e334c1b26433177e924366baee22fa6996b75596d9`
    - `styles/edge-empty-cursor.json` `e1eb07f000387d3e21d305f086ee0134b952f2b2e1ee811a294307c028c5854b`
    - `styles/edge-repeated-tag.json` `e1eb07f000387d3e21d305f086ee0134b952f2b2e1ee811a294307c028c5854b`
    - `styles/edge-whitespace-tag.json` `e1eb07f000387d3e21d305f086ee0134b952f2b2e1ee811a294307c028c5854b`
    - `styles/empty-first-page.json` `51153a9d4583fd47975c6aabfb2337b1a9f60ae8359d506fe5ce3585b8f170f3`
    - `styles/error-http-with-cursor.json` `19d107e508912e1a5e1ee58f8519e5cee345e58846602cac38e23629036ae8ef`
    - `styles/error-http.json` `19d107e508912e1a5e1ee58f8519e5cee345e58846602cac38e23629036ae8ef`
    - `styles/error-malformed.json` `19d107e508912e1a5e1ee58f8519e5cee345e58846602cac38e23629036ae8ef`
    - `styles/error-network-with-cursor.json` `19d107e508912e1a5e1ee58f8519e5cee345e58846602cac38e23629036ae8ef`
    - `styles/error-network.json` `19d107e508912e1a5e1ee58f8519e5cee345e58846602cac38e23629036ae8ef`
    - `styles/filtered-empty-drained.json` `e41a0e899ba4b8eec34e03ec9c96ab35f38f81ff0ca2f3013c9765f06dc69dfa`
    - `styles/filtered-empty-no-cards-tagged.json` `92b0b7e6ceeefd86ab91e4a1083b227497153e30529d59970e4018359830ee88`
    - `styles/ok-first-page.json` `e1eb07f000387d3e21d305f086ee0134b952f2b2e1ee811a294307c028c5854b`
    - `styles/ok-last-page.json` `55a26546233d86e9aabe9bef28d430e0b9ea7a5a994060811fa775fc3ec35719`
    - `styles/tag-not-promoted.json` `bd0b48930d7f128ecc54d80fd8c0808fcd7e2be94df2576670b8cecb077530a7`
    - `styles/tag-promoted.json` `02f35be363feb0756d0d6d68fa7d6cce4e9758b8d2f1e438cc2e00ec8e3262fe`
    - `styles/tag-untrimmed.json` `2e63f2aa89ccde40c34beaaf5cc200b0d5fcb329fc1810a5e6dae77cb833da16`
- [ ] **O2** (AC4, AC5, AC2, AC3, AC1): New unit tests and guard cases are written and fail for the right reason.
  - Tests:
    - `features/feed/lib/search-params.test.ts`
    - `features/feed/api/load-feed-state.test.ts`
    - new cases in `features/feed/conventions.test.ts` (layout, deep-import ban, export surface, no self-import, no client import of the barrel or `api/`, type-only `api/` imports)
  - Red (2026-10-03, `npm test`): 3 files failed, 7 passed; 62 tests passed, 2 failed. `features/feed/lib/search-params.test.ts` and `features/feed/api/load-feed-state.test.ts` fail at import (`Failed to resolve import "./search-params"` / `"./client"`: the modules are not in `api/` or `lib/` yet). In `conventions.test.ts` the failing cases are `AC1: the feature root holds only index.ts, conventions.test.ts and api/ components/ lib/` (root still holds 18 files) and `AC2: the barrel exports exactly ...` (`Cannot find module '/features/feed/index'`). T29 to T31 pass. The other new guard cases pass on today's tree because nothing violates them yet. Each was shown to fail with temporary violating files, since deleted: `app/tmp-violation-a.tsx` (deep import), `features/feed/components/tmp-violation-b.tsx` (`'use client'` + `from '..'`), `features/feed/lib/tmp-violation-c.ts` (value import of `../api/client`) made 4 scan cases fail (deep-import, barrel self-import, client-import, type-only api/). The barrel-surface case was also run against a temporary 3-name stub (pass) and a wrong stub (fail), then removed. Pure checkers are additionally exercised on inline sources (`AC2 guard`, `AC3 guard` cases).
  - Note for O3: `lib/` and `api/` already exist holding only the two new tests. `typecheck` is red until O3/O4 (TS2307 on those modules), as expected; `lint` has 0 errors.
  - Green: recorded under O3 and O4.
- [ ] **O3** (AC1, AC9, AC8): Files are moved with `git mv`, intra-feature imports are fixed, and the codegen output path is updated.
  - Tests: the 7 existing test files, moved
  - Red: not applicable (migration)
  - Green: `npm test` (55 original tests plus O2 tests). `npm run generate:types && git status --porcelain features/feed` shows no diff. The SHA-256 values match the Baseline section. `git diff -M --stat d343830 -- features/feed` shows renames.
- [ ] **O4** (AC2, AC3, AC4, AC5, AC6): Add `lib/search-params.ts`, `api/load-feed-state.ts` and `index.ts` with the three-name surface. Rewrite `app/page.tsx` to import only from `@/features/feed`.
  - Tests: as in O2
  - Red: O2's result
  - Green: `npm test`, result to be recorded. `grep -nE "try|catch|console|\.\./features" app/page.tsx` should print nothing.
- [ ] **O5** (AC7, AC6): No behavior or HTML regression.
  - Tests: `e2e/feed.e2e.ts`
  - Green: `npm run test:e2e` run without `--update-snapshots`. The baseline SHA-256 values must equal O1's, and `git status e2e/__baseline__` must be clean.
- [ ] **O6** Migration (AC8): `app/page.tsx` is the only external consumer and is migrated in O4. The 7 moved tests change only import, mock and path lines, which a review of `git diff -M d343830 -- features/feed` must confirm. `scripts/generate-api-types.mjs` points `OUT` at the new path.
- [ ] **O7** Docs: the documentation role does this after the audit. The executor does not edit these files.
  - `AGENTS.md` § Components tree.
  - The repo-root `README.md` "Phase 2 — Web Feed" path references (around lines 702–736), plus a `npm run test:e2e` runbook line.
  - `specs/current/web-feed.md`: WEB-2, WEB-9 and WEB-R3 paths and invariant 3. `harny-sync` handles these in archive mode.
  - ADR 0008, only if the human asks for it.
  - Leave the `feed.module.css` header comment unchanged (WEB-9).
- [ ] **O8** Broader suite against the baseline (AC10, WEB-11):
  - Run `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e`. Lint may show only the pre-existing warning.
  - `git diff d343830 -- package.json` should show only `@playwright/test` and `test:e2e`.
  - Run the WEB-11 local `npm run dev` smoke check against the real `feed-api`.
- [ ] **O9** Independent audit: the verdict will come from `audit.md` (not yet written)

## Working state
- Updated: 2026-10-03
- Outcome: none started
- Phase: spec drafting complete; awaiting human approval of intent revision 1
- In progress: nothing
- Last command: `npm test` passed 55/55 (baseline)
- Next step: after approval, the test-writer starts O1, capturing the e2e baseline on the unmodified tree before anything is moved

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
The specs are drafted and awaiting the human gate. Resume at O1. The baseline must be captured before any file under `features/feed/` or `app/` is touched.
