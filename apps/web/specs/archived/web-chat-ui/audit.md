# Audit: Web Chat UI

Round 1, 2026-10-22. Branch `feat/web-chat-ui`, base `48334d8`, nothing committed. Reviewed the
working tree (tracked and untracked) against `intent.md` revision 2, `execution-plan.md` and
`tasks.md`. Every changed and new file was read in full. Conventions came from `AGENTS.md` (WEB-1 to
WEB-11, barrel rules) via `harny-standards`, and test quality was judged with `high-value-tests`.
The auditor did not read `.env.local`, did not run any `aws`, `vercel` or `cdk` command, and did not
print any credential value.

Commands rerun by the auditor in `apps/web` (Node v24.16.0):

| Command | Result | Label |
|---|---|---|
| `npm run lint` | 0 errors, 1 warning (the existing unused `eslint-disable` in `features/feed/api/types.generated.ts`, same as baseline) | rerun (at the caller's request; see F6) |
| `npm run typecheck` | clean | rerun (at the caller's request; see F6) |
| `npm test` | 18 files, 237 tests passed (baseline 87) | rerun |
| `npm run build` | OK; route table `ƒ /`, `○ /_not-found`, `ƒ /api/chat` | rerun |
| `npm run test:e2e` | 32 passed: 9 `chat.e2e.ts` and 23 `feed.e2e.ts`, including all 17 baseline scenarios; no `--update-snapshots` | rerun |
| Client-bundle scan of `.next/static` for `CHAT_API`, `AWS4-HMAC`, `aws4_request`, `execute-api`, `secretAccessKey`, `handleChatRequest`, `chat_request`, `AKIA…`/`ASIA…` | 0 files for each. Sanity check: `/api/chat` and the "Thinking..." copy are present, 1 file each | rerun |
| `.next/server` scan for `AKIA…`/`ASIA…` (the build loaded `.env.local`) | 0 files, so env is read at runtime and never inlined | rerun |
| Route log lines from the e2e run (`e2e/.tmp/app-*.stderr.log`) | only `{"event":"chat_request","outcome":"busy"|"timeout","duration_ms":N}`; 0 hits for the fake key, fake secret, stub URL or question text | rerun |
| `npm view aws4fetch time` / `dependencies` | 1.0.20 published 2024-08-28 (about 14 months old), latest, no dependencies | rerun |
| `git diff --stat -- e2e/__baseline__ e2e/feed.e2e.ts app/globals.css features/feed/components/feed.module.css` | empty | rerun |
| Working-tree secret scan (191 tracked and untracked non-ignored files, `.env.local` excluded) | no `AKIA`/`ASIA` id, no 40-character secret. The only `execute-api` hosts are the existing feed-api ids in `.env.example` line 10 and `specs/archived/web-feed-ui/*` (tracked, unchanged), the `<api-id>` placeholder, and two fake hosts in the T29 guard test. No chat API id anywhere | rerun |

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `chat-widget.tsx`: closed by default (`useState(false)`). The toggle has `aria-expanded`, `aria-controls={panelId}`, and `aria-label` "Open chat"/"Close chat". The panel is `role="dialog"` with `aria-label`. Escape is handled on the widget wrapper. Focus goes to the textarea on open (effect) and back to the toggle on close. 7 component tests and 2 e2e tests pass (rerun). Note F8 on `aria-controls` while closed. |
| AC2 | PASS | `message-list.tsx` shows the pending user message plus a `role="status"` "Thinking..." line. `source-list.tsx` renders `<a href={url}>[n] title source</a>` and returns `null` for an empty list. Component tests check the links, href, `[n]`, title, source name and the empty list. The e2e test sees the stubbed answer with 3 links to `https://example.test/source-n` (rerun). |
| AC3 | PASS (see F1) | `history.ts`: `isValidHistory` (array, even length, alternating roles starting with `user`, string text) and `trimHistory` (`slice(-20)`, each text cut to 4000) run in `handle-chat-request.ts` before the call. Tests: 12 turns forward turns 3 to 12 plus the question; 20 items unchanged; a 5000-character item is cut to 4000; bad shapes get 400 and the backend is not called. History grows by one pair only on success (reducer and component tests, rerun). The rules match `src/chat/request.py` and `config.py` defaults (10 turns, 4000) except the backend's non-blank `text` rule (`history_item_text_invalid`, request.py:61-62), which the route does not check (F1). |
| AC4 | PASS | UI: `submit()` trims, blocks a blank question ("Type a question first.") and one over 1000 characters with a `role="alert"` message, and sends no request. Route: blank, empty, 1001 characters, missing, non-string, missing body, non-JSON, non-object and over 524,288 bytes all get 400 `{"error":"invalid_request"}` and `fetch` is never called. Exactly 1000 is accepted. Unit, component and e2e tests pass (rerun). Edge note F3 (UTF-16 counting). |
| AC5 | PASS | `handle-chat-request.ts` `REPLY` matches the plan's table row by row: 400→400 `invalid_request`, 429→429 `busy`, 504 or abort→504 `timeout`, 502, bad 200 or network error→502 `upstream_failure`, 403, other non-2xx or missing/blank env→503 `unavailable`, a throw→500 `internal_error`. The body is exactly `{"error":code}`. `detail`, status, URL and key are never forwarded (asserted per row). There is one log line, `{event,outcome,duration_ms}`, with no question, history, answer, key, secret, URL or backend detail (asserted per row, and confirmed in the real e2e stderr). The panel has 6 distinct generic copies plus Retry. The question is restored to the input, and the conversation is kept. Component and e2e (429, 504) tests pass (rerun). AC5's list of failure classes is grouped into the plan's six approved codes (403, backend 5xx and missing config share `unavailable`), as the approved Decision 5 specifies. |
| AC6 | PASS | `route.ts`: `runtime='nodejs'`, `dynamic='force-dynamic'`, `maxDuration=40`. `backend.ts`: `new AwsClient({service:'execute-api', region:'us-east-1', retries:0}).sign(\`${base}/v1/chat\`, POST)`, then one global `fetch(signed, {signal})` with a 30 s abort. `AwsClient.fetch` is never used (grep). Env is read per request through `process.env[name]` in `handle-chat-request.ts` only (a test proves the per-request read). The unit test checks `AWS4-HMAC-SHA256`, `Credential=<fake id>/…/us-east-1/execute-api/aws4_request`, a 64-hex signature, and that the secret is absent from the URL, headers and body. The stub returns 403 to any request without that scope, so the e2e 200 shows a signed call. The e2e test sees exactly one POST, same-origin `http://127.0.0.1:3100/api/chat`. Bundle scans are clean. `.env.example` holds placeholders only (rerun). |
| AC7 | PASS | `app/page.tsx` renders `<FeedView/>` and `<ChatWidget/>` as siblings. The e2e test shows no toggle or dialog inside the `feedPage` root. The 17 baseline scenarios pass byte-identically, and `e2e/__baseline__`, `feed.e2e.ts`, `globals.css` and `feed.module.css` are unchanged. The only `features/feed` diff is the T29 narrowing. The feed unit suite passes. There is no `console` call in components or lib (grep), and component and e2e console-clean tests pass (rerun). |
| AC8 | PASS | Every `var(--…)` in `chat.module.css` (23 tokens) is defined in `app/globals.css`. There are no hex, rgb or hsl colours, and every padding, margin, gap and radius is a token or `0`. The remaining literals are font sizes (same convention as `feed.module.css`), 1px and 2px border and outline widths, `z-index`, and sizes. Theme follows `prefers-color-scheme` through the tokens, with no `data-theme`. The CSS check and the e2e light and dark `--surface-card` comparison pass (rerun). |
| AC9 | PASS | `e2e/chat.e2e.ts` covers open, ask, answer with 3 sources, 429 with retry, and 504, against the node:http stub with fake credentials (`FAKE-E2E-KEY-ID-0001`) set explicitly in `launch-apps.mjs`, which overrides `.env.local`. Signing has a unit test (`backend.test.ts`). Offline run passes (rerun). |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| Browser calls only the same-origin route; no `NEXT_PUBLIC_`; no `execute-api` host in browser code; no `"use client"` module imports the barrel or `api/` | PASS | `send-turn.ts` fetches `'/api/chat'` only. The only `"use client"` module is `chat-widget.tsx`, which imports `lib/*` and `components/*`, and `lib`/`components` reach `api/` only through `import type`. Guards in `features/chat/conventions.test.ts` (with violation self-tests) and feed T29/T30 pass. Bundle scan is clean (rerun). |
| Node.js runtime; SigV4 `execute-api`/`us-east-1`; only `POST {CHAT_API_BASE_URL}/v1/chat` | PASS | `route.ts` line 3; `backend.ts` lines 36-47; the URL is asserted in `backend.test.ts` and `handle-chat-request.test.ts`. A trailing slash on the base is stripped (`handle-chat-request.ts:72`). |
| Env names `CHAT_API_*`, not `AWS_*`; read per request, never at import, never logged or returned | PASS | `handle-chat-request.ts:42-69` (inside the handler). Credential names appear only under `features/chat/api/` (guard). The per-request read is tested. Logs and bodies are leak-tested with fake values. |
| Exactly one backend call per turn, no retry at any layer | PASS | `sign()` plus one `fetch` with `retries: 0`. `aws4fetch` `sign()` (dist lines 42-61) does no network I/O. There is no loop in `backend.ts`, `handle-chat-request.ts` or `send-turn.ts`. Tests assert `fetch` is called once on 429, 502, 504, network error and abort, and once per mapping row. Playwright `retries: 0`. |
| Frozen contract; response shape-checked; a mismatch is an upstream failure | PASS | `lib/chat-response.ts` checks `answer` and each source's `n,title,url,source,published(null|string),score` against `build_sources` in `src/chat/graph.py`. A mis-shaped or non-JSON 200 gives 502 `upstream_failure` (tested). |
| Caps 1000 / 20 items / 4000 / 524,288 bytes | PASS | `lib/limits.ts`. They match `src/chat/config.py` defaults (1000, 10 turns, 4000) and the edge cap. Boundary tests for 1000/1001, 20/24 items, 4000/4001/5000/9000 and a body over 524,288 bytes. See F1 (blank text) and F3 (code units). |
| Fixed error codes with generic copy; one-line JSON logs without text, credential or URL | PASS | `REPLY` table, `ERROR_COPY` (6 entries, tested for no status, URL, code-name or trace). Log format confirmed in real e2e stderr. |
| Styling with tokens only; `globals.css` and `feed.module.css` not edited | PASS | See AC8. `git diff` is empty for both. |
| `e2e/__baseline__` never regenerated; 17 baseline scenarios pass | PASS | `git diff --stat` is empty; 17/17 baseline scenarios pass (rerun). |
| No `.sort(`/`.reverse(` under `features/` (non-test); no Vercel/cdk/aws command | PASS | grep: none in non-test chat source (feed T31 passes). `package.json` scripts are unchanged. No such command is evidenced in `tasks.md` (reused; the executor's shell history is unavailable). |
| Agents never read, print or write the real key; tests use fake values | PASS | All credentials in tests, stub and launcher are obvious fakes. No key material in the tree (scan). `.env.local` is git-ignored (`.gitignore:34`). Whether the executor read `.env.local` is unavailable, but nothing derived from it appears anywhere. |
| Dependencies: only `aws4fetch`, exact pin, at least two weeks old | PASS | `package.json` diff: `"aws4fetch": "1.0.20"` (exact). The `package-lock.json` diff is exactly the root dependency entry and `node_modules/aws4fetch`. No other dependency or dev dependency changed. Published 2024-08-28; zero transitive dependencies. |
| Ownership | PASS | Changed and new files are all in Ownership. `CLAUDE.md` (`@.claude/memory/web-chat-ui-handoff.md`) and `.claude/memory/` both date from 2026-10-21 15:33, before the spec (the handoff, not executor work). `../../specs/archived/chat-agent-runtime/.sdd/` (2026-10-14) is unrelated and older. |

### Executor's disclosed deviations
| Deviation | Acceptable | Reason |
|---|---|---|
| `lib/chat-response.ts` added (shared `isChatResponse`) | Yes | It is a compliant alternative: one shape check used by both `api/backend.ts` (server boundary) and `lib/send-turn.ts` (browser boundary). It is pure, uses only `import type` from `api/`, and passes the layout, barrel and `"use client"` guards. It avoids two copies of the contract check. |
| Textarea cleared on send and restored on failure | Yes | It satisfies AC5 "the input keeps the question" (component and e2e tests). A minor UX edge is noted as F10. |
| Enter submits, Shift+Enter inserts a newline, Send disabled while pending | Yes | It keeps a single in-flight turn, consistent with the one-call rule. `submit()` also guards on `state.pending`, so Enter cannot double-send. It does not conflict with Decision 9. |

### Conventions (`harny-standards`, `AGENTS.md`)
WEB-1 PASS (extended to chat, guarded). WEB-2: generated types untouched. WEB-3 PASS. WEB-4 and WEB-5: feed unchanged. WEB-8 and WEB-9 PASS. WEB-10: npm only. WEB-11: no deploy. Barrel-only imports PASS (chat barrel exports exactly `ChatWidget`, `handleChatRequest`, tested). Style: small modules, tests next to source. One documentation drift: the `AGENTS.md` WEB-1 wording (F2).

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `features/chat/components/chat-widget.test.tsx` "open and close" (7); `e2e/chat.e2e.ts` "chat widget (AC1)" (2) | PASS |
| AC2 | `chat-widget.test.tsx` "asking and answering" (4); `lib/send-turn.test.ts` 200 mapping; `lib/conversation.test.ts`; `e2e/chat.e2e.ts` "shows the stubbed answer…" | PASS |
| AC3 | `lib/history.test.ts` (14); `api/handle-chat-request.test.ts` "history trimming" and local validation; `chat-widget.test.tsx` "multi-turn history"; `conversation.test.ts` | PASS (no blank-text case, F1) |
| AC4 | `handle-chat-request.test.ts` local validation; `chat-widget.test.tsx` "question limits"; `e2e/chat.e2e.ts` "question limits" | PASS |
| AC5 | `handle-chat-request.test.ts` mapping table, missing config, logging; `backend.test.ts` results; `send-turn.test.ts`; `chat-widget.test.tsx` "failure states"; `e2e/chat.e2e.ts` 429 and 504 | PASS |
| AC6 | `api/backend.test.ts` signed request and one attempt; `handle-chat-request.test.ts` per-request env and leaks; `features/chat/conventions.test.ts`; `features/feed/conventions.test.ts` T29 and guard case; e2e signed-stub answer and single same-origin POST | PASS (manual tier is H1, F7) |
| AC7 | the existing feed suites, unchanged and passing; `e2e/feed.e2e.ts` 17 baselines; `chat-widget.test.tsx` "console"; e2e console-clean and outside-root | PASS |
| AC8 | `components/chat-css.test.ts` (with checker self-tests); e2e "theme (AC8)" light and dark | PASS |
| AC9 | `e2e/chat.e2e.ts` (9); `backend.test.ts` signing | PASS |

Test integrity: every test file, the stub and the launcher (last modified 21:57:44 to 22:00:40) are older than every implementation file (22:06:02 to 22:06:37), so the tests were not edited after the green phase. Each outcome's red evidence is "module missing"; O4 has no recorded red line (F9). The tests assert behavior rather than tautologies: mapping rows, call counts, leak markers and boundaries. The source-reading tests (conventions guards, the CSS token check) are the structural invariants that § Validation approves, and each has a self-test that shows it fires on a violation. No dead test seam was found: `timeoutMs` is exercised, and env stubs are used by the code.

### Tier Results
Checked against `execution-plan.md` § Validation. No dev dependency, config file or script was added (`package.json` change is the runtime `aws4fetch` only). The stub and launcher extensions are the "e2e chat stub" setup named in rows AC2 and AC9.

| Tier | Status | Evidence |
|---|---|---|
| unit (Vitest, pure and route logic, guards, CSS rule) | PASS | Tests found: `history`, `send-turn`, `conversation`, `backend`, `handle-chat-request`, `chat-css`, `features/chat/conventions`, feed T29 guard. ACs verified: AC3, AC4, AC5, AC6, AC8. Setup matches (stubbed `fetch`, fake env). Ran: `npm test` 237/237 (rerun). Finding: none. |
| unit (component, Vitest with jsdom and Testing Library) | PASS | Tests found: `chat-widget.test.tsx` (26). ACs verified: AC1 to AC5 and AC7. Setup matches (none). Ran: rerun. Finding: none. |
| e2e (Playwright) | PASS | Tests found: `e2e/chat.e2e.ts` (9) plus the unchanged `feed.e2e.ts`. ACs verified: AC1, AC2, AC4 to AC9. Setup matches (stub `POST /<scenario>/v1/chat` with SigV4 scope check; `launch-apps.mjs` fake `CHAT_API_*`). Ran: `npm run test:e2e` 32/32 offline (rerun). Finding: none. |
| manual (human, AC6, WEBCHAT-R2) | N/A (not run) | Not run: needs the real key in `.env.local` (H1), which the auditor must not read. Finding F7 (LOW). |

## Findings
| Id | Severity | Closure condition | Status |
|---|---|---|---|
| F1 | MEDIUM (AC3; binding constraint "caps/contract"; plan Decision 6) | `isValidHistory` (or the route) treats an item whose `text.trim()` is empty as `invalid_request`, matching the backend rule `history_item_text_invalid` (`src/chat/request.py:61-62`). Add a `handle-chat-request.test.ts` case where a blank or whitespace history text gets 400 and `fetch` is not called. Today such a history passes the route, reaches the backend (using a throttle slot) and is rejected there for a history rule, so AC3's "never rejected by the backend for a history rule" does not hold for it. The client can produce it only if the agent returns a whitespace-only answer (`chat_app.py:101` replaces only an empty one), and then every later turn of that conversation fails until reload. The visitor's outcome is the same 400 code, and every rule AC3 lists is met, so this is rated a deviation rather than an unmet AC. The human may treat it as blocking. | Open |
| F2 | MEDIUM (AC6 and the WEB-1 docs; plan "Consumers": `AGENTS.md`) | `AGENTS.md` "WEB-1" still says "no `execute-api` literals", but T29 now forbids only the host form and `features/chat/api/backend.ts` uses `service: 'execute-api'`. Update the bullet to the host-literal wording and record the T29 narrowing ADR (0032+ series) at archive time. | Open |
| F3 | LOW (AC3, AC4; caps constraint) | The UI and route measure `string.length` and cut with `slice` in UTF-16 code units, while the backend counts code points. As a result, a question of more than 500 astral characters is rejected though the backend would accept it, and the 4000 cut can split a surrogate pair. It is never a history-rule rejection, though a lone surrogate could become an upstream failure. Count and cut by code points, or record this as an accepted edge. | Open |
| F4 | LOW (AC5, timeout mapping) | `backend.ts`: the 30 s abort also covers `res.json()`, and an abort while the body is read is caught by the inner `catch` and reported as `upstream_failure`, not `timeout`. Map an `AbortError` there to `timeout`, or accept it. | Open |
| F5 | LOW (body cap constraint) | `handle-chat-request.ts` checks the byte cap after `request.text()` has read the whole body when there is no `Content-Length` (chunked), so a very large body is buffered before the 400. Platform body limits cap this in production. Stream-limit the read, or accept it. | Open |
| F6 | LOW (`harny-feedback` verification) | The CI workflow `.github/workflows/harny-feedback-apps-web.yml` exists but has no run against this change (nothing is committed or pushed), and the Stop-hook evidence is indirect (`.sdd/feedback/.turns/` touched 2026-10-22 21:56, with no persisted `N of M command(s) ran` line). The auditor reran lint and typecheck only because the caller explicitly asked. Push the branch and confirm the workflow run is green with N > 0. | Open |
| F7 | LOW (tier: manual, AC6 and AC2, WEBCHAT-R2) | The human runs H1 and records the latency and a `[1]` citation. | Open (human) |
| F8 | LOW (AC1, accessibility) | `aria-controls` on the toggle names the panel id while the panel is not rendered (closed). Set it only when open, or keep the panel mounted and `hidden`. | Open |
| F9 | LOW (`tasks.md` hygiene; outcome evidence) | `tasks.md` Baseline says "Branch: main" (work is on `feat/web-chat-ui`). The Checkpoint still says "awaiting the human's approval". O4 has no Red evidence line. Build and e2e baselines were never recorded under Pre-existing failures. The executor updates `tasks.md`. | Open |
| F10 | LOW (deviation 2, UX) | If the visitor edits the textarea while a turn is pending and the turn fails, `setDraft(question)` overwrites the edit. Restore only when the draft is empty, or accept it. | Open |

Notes (not findings): the lint warning is pre-existing (baseline 1). `.env.example` line 10 holds the existing real feed-api URL (tracked before this change and public by design). Chromium may log its own "Failed to load resource" line for a 429 or 504 response; the widget itself writes nothing to the console. WEBCHAT-R1 (no per-visitor limit) and WEBCHAT-R3 (Vercel duration versus `maxDuration` 40) are accepted reservations from the plan.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-22 | APPROVED WITH RESERVATIONS | All 9 ACs and all binding constraints pass on rerun evidence (lint, typecheck, 237 unit tests, build, 32 e2e, bundle and secret scans). No CRITICAL or HIGH findings. Two MEDIUM: F1 (blank history text reaches the backend) and F2 (`AGENTS.md` WEB-1 wording). Eight LOW. |

## Final verdict
APPROVED WITH RESERVATIONS

**Summary**: The chat widget, the SigV4 route and their tests meet every acceptance criterion and binding constraint on independently rerun evidence. The key stays server-side, each turn makes exactly one unretried backend call, the error mapping matches the plan, and the feed baselines are byte-identical. The route's history check misses the backend's non-blank-text rule (F1), and `AGENTS.md` WEB-1 is now stale (F2). Both should be fixed before merge but do not block.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F1: reject blank or whitespace history `text` in the route, with a test.
- F2: update the `AGENTS.md` WEB-1 wording to the host-literal rule.
- F6: get a green `harny-feedback-apps-web.yml` run after pushing.

**Recommendations** (nice to have):
- F3 (code-point counting), F4 (abort during body read maps to timeout), F5 (stream-limited body read), F8 (`aria-controls` while closed), F9 (`tasks.md` hygiene), F10 (do not overwrite a draft edited while pending).

### Close-out checklist
- [ ] **H1** (human, AC6, AC2, WEBCHAT-R2): put the caller key in `apps/web/.env.local`, run `npm run dev`, ask one real question, and record the latency and the `[1]` citation. Still open.
- [ ] **H2** (human, WEBCHAT-R3): check the Vercel plan's function duration against `maxDuration` 40 and set the three `CHAT_API_*` variables (not `AWS_*`) in the Vercel project. Still open.
- [ ] F1 and F2 fixed by `harny-implement` (recommended before merge); a re-audit round confirms their closure conditions.
- [ ] Commit and push `feat/web-chat-ui`; confirm the `harny-feedback-apps-web.yml` run is green (F6).
- [ ] Root `README.md` "Phase 3" chat notes handed to the human or `harny-document` (plan "Consumers").
- [ ] ADRs from 0032 (signing library, route as sole caller with fixed codes, T29 narrowing, no per-visitor limit) via `harny-adr`.
- [ ] At archive: create the `web-chat` capability and amend `web-feed` invariant 3 in `specs/current/`. Delete the handoff `.claude/memory/web-chat-ui-handoff.md` or fold it into the spec, and remove its `@` import from `apps/web/CLAUDE.md`, as the handoff itself asks.
