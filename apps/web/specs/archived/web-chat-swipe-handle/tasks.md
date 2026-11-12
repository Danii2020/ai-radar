# Tasks: Web Chat Swipe Handle

## Status
Implemented and audited 2026-11-11 (APPROVED WITH RESERVATIONS, round 1); shipped and archived 2026-11-11. O8 (real-device swipe check) remains a human reservation

## Baseline
- Base commit: 846a1c1 (Merge pull request #16 from Danii2020/feat/feed-prev-cursor)
- Branch: feat/web-chat-swipe-handle
- Interpreter: Node v24.16.0; Next 16.3.5, React 19.2.8, vitest ^4.1.11, @playwright/test 1.64.1
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test:e2e`
- Pre-existing failures: not recorded before the first edit (audit F1). The auditor showed the one lint warning
  (`features/feed/api/types.generated.ts`, unused eslint-disable) predates this change

## Outcomes
- [x] **O1** (AC1, AC7): On a phone the launcher renders as the right-edge tab (icon, no visible text, lower third,
  20 to 24 px wide, at least 44 px tall, token colours, focus ring inside the viewport); desktop keeps the pill.
  - Tests: `e2e/chat-swipe.e2e.ts` ("edge tab", "desktop"); `features/chat/components/chat-css.test.ts` (existing)
  - Red:
  - Green:
- [x] **O2** (AC3, AC4): The gesture rule (40 px, 2:1, touch or pen only, phone query only) and swipe-left-to-open
  on the tab, with the trailing click suppressed and non-swipes ignored; vertical page scroll from the tab kept.
  - Tests: `features/chat/lib/swipe.test.ts` (if the module is added); `features/chat/components/chat-widget.test.tsx`
    (`describe("phone gestures")`); `e2e/chat-swipe.e2e.ts` ("swipe left", "does not open")
  - Red:
  - Green:
- [x] **O3** (AC5): Swipe right on the open sheet closes it through the existing `close()`, focus returns to the
  tab, the conversation is kept, and gestures starting in the textarea or a horizontally scrollable element are
  ignored.
  - Tests: `features/chat/components/chat-widget.test.tsx` (`describe("phone gestures")`); `e2e/chat-swipe.e2e.ts`
    ("swipe right")
  - Red:
  - Green:
- [x] **O4** (AC2, AC6): Tap and keyboard open on a phone, every close returns focus to the tab, and anything this
  feature animates is off under reduced motion.
  - Tests: `e2e/chat-swipe.e2e.ts` ("tap and keyboard", "reduced motion")
  - Red:
  - Green:
- [x] **O5** (AC9): The new e2e file runs offline against the local stub, with a trusted-touch CDP helper and a
  local-only request assertion.
  - Tests: `e2e/chat-swipe.e2e.ts`; helper `e2e/touch.ts` (suggested name)
  - Red:
  - Green:
- [x] **O6** Migration (AC7, AC8): `e2e/chat.e2e.ts`, `e2e/layout.e2e.ts`, `e2e/chat-rate-limit.e2e.ts`,
  `e2e/feed.e2e.ts` (17 baselines, no snapshot update), `chat-widget.test.tsx` existing tests,
  `chat-css.test.ts` and `features/chat/conventions.test.ts` pass unedited; `git diff --stat` shows no change to
  `features/chat/api/`, `features/chat/index.ts`, existing `features/chat/lib/*.ts`, `app/`, `features/feed/`,
  `package.json` or `package-lock.json`.
- [x] **O7** Docs: `apps/web/AGENTS.md` components block names the edge tab and swipe gestures on the chat-widget
  line, and the new `lib/` module if one is added.
- [ ] **O8** Human real-device check (intent Q1, not an executor task): on an Android phone with gesture
  navigation and on an iPhone in Safari, record whether swipe left on the tab opens the sheet or is taken by the
  OS or browser, and confirm tap opens and swipe right closes. Until done, record it as unavailable, never as a
  pass. Status 2026-11-11: the human confirmed on an iPhone (Brave) that tapping the tab opens the chat (after the
  dev-origin fix in `next.config.ts`); swipe left and swipe right on a real phone were not separately confirmed,
  and Android gesture navigation was not checked. Stays open.
- [x] **O9** Broader suite vs baseline: `npm run lint && npm run typecheck && npm test && npm run build &&
  npm run test:e2e`, compared with the Baseline above.
- [x] **O10** Independent audit: verdict from `specs/web-chat-swipe-handle/audit.md`.

## Working state
- Updated: 2026-11-11
- Outcome: O1 to O7 and O9 done; O8 open (human); O10 done (APPROVED WITH RESERVATIONS)
- Phase: shipped, documented and archived
- In progress: nothing
- Last command: `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` (auditor rerun, green)
- Next step: the human checks the swipe gestures on a real phone (O8); a green `harny-feedback-apps-web.yml` run on the PR

## Execution notes (executor)
- Baseline not recorded before edits (red tests already present). After: lint 0 errors (1 pre-existing warning in
  features/feed/api/types.generated.ts), typecheck clean, vitest 433/433, build ok, e2e 61/61.
- Green: swipe.ts (new), chat-widget.tsx (pointer handlers on wrapper, click suppression, icon span/svg),
  chat.module.css (phone edge tab, touch-action pan-y on .toggle, .panel and .scroll; the scroll container needs its
  own value because touch-action intersection stops at it).
- O8 unavailable: real-device check is the human's step. O10 pending audit.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Implemented, audited and archived 2026-11-11. Remaining: O8 real-device swipe check (human). The human confirmed on an iPhone (Brave) that tapping the edge tab opens the chat; swipe left and right were not separately confirmed.
