# Changelog

All notable changes to `apps/web` are recorded here, in the Keep a Changelog format.

## [Unreleased]

### Added
- Response cache for `POST /api/chat` (`web-chat-response-cache`, 2026-11-18). A first-turn question (no history) is
  answered from the cache when the same question, normalized by trimming, collapsing whitespace and lower-casing, was
  answered within `CHAT_CACHE_TTL_S` seconds (default 21600; `0` is off, otherwise 60 to 86400). A hit makes no chat API
  call and counts only against the burst limit (a new burst-only limiter mode); a miss behaves as before and stores the
  answer after the live call. Only successful answers are stored, as `{answer, sources}` under an HMAC-keyed
  `chat-cache:{v1}:<digest>` key. Every cache failure is a miss (fail open), and the `chat_request` log line gains a
  text-free `cache` field (`hit`, `miss`, `skip`, `error`; absent when off). New module
  `features/chat/api/response-cache.ts`, a fourth `next start` e2e instance (port 3103) and a stub request counter. Audit:
  APPROVED WITH RESERVATIONS (round 1, a self-audit by the implementing session): 496 unit and 64 e2e tests green.
- Vercel Web Analytics (`web-chat-response-cache`, 2026-11-18): `@vercel/analytics` 2.0.1, rendered by `app/layout.tsx`
  only when `VERCEL` is set (page views only; nothing from the chat). The dependency rule was amended for it (ADR 0058).
  Enabling Web Analytics for the project in the Vercel dashboard is a human step.
- Per-visitor and global limit on `POST /api/chat` (`web-chat-visitor-rate-limit`, 2026-11-18). Defaults: 5 turns per
  visitor per 60 s, 20 per visitor per UTC day, 50 for everyone per UTC day, checked after validation and before the
  one signed backend call. A limited request gets 429 `{"error":"rate_limited"}` with `Retry-After` (a seventh fixed
  code) and the panel shows its own message. Counters are kept in Upstash Redis through one `EVAL` over its REST API
  (no new dependency), keyed by an HMAC-SHA-256 of the visitor with `CHAT_RATE_LIMIT_SALT`; the store fails closed
  (503 `unavailable`), and an in-process store serves local runs, unit tests and e2e. New modules
  `features/chat/api/rate-limit.ts`, `rate-limit-config.ts` and `visitor.ts`; a third `next start` instance (port 3102)
  and `e2e/chat-rate-limit.e2e.ts`. Audit: APPROVED WITH RESERVATIONS (round 2): 391 unit and component tests and 53
  e2e tests green on the auditor's rerun.
- Phone edge tab for the chat launcher (`web-chat-swipe-handle`, 2026-11-11). At 640 px and narrower the launcher is a
  24 by 64 px tab with a chat icon, flush with the right edge in the lower third of the viewport. Tap, Enter and
  Space open the sheet; a touch or pen swipe left on the tab opens it, and a swipe right on the open sheet closes it
  (40 px threshold, 2:1 ratio, ignored from the textarea and from horizontally scrolling code blocks). New pure
  module `features/chat/lib/swipe.ts`; new e2e file `e2e/chat-swipe.e2e.ts` with a trusted-touch CDP helper
  `e2e/touch.ts`. No new dependency. Audit: APPROVED WITH RESERVATIONS (round 1): 433 unit and 61 e2e tests green on
  the auditor's rerun; real-device checks of the swipe gestures are still open (WEBCHAT-R10).
- `allowedDevOrigins` (`192.168.*.*`, `10.*.*.*`) in `next.config.ts`, dev only, so the app hydrates when opened
  from a phone over the LAN. Not covered by the audit; confirmed by hand on an iPhone (Brave), where the tab opens
  the chat.

### Changed
- On phones the chat launcher is 24 by 64 px, below the 44 by 44 px hit area WEBCHAT-1 set. It meets WCAG 2.2 AA
  2.5.8 (24 by 24); desktop keeps 44 by 44 (ADR 0056).
- Feed pager links (`.pagerLink` in `features/feed/components/feed.module.css`) use `min-height`, 8 px vertical
  padding, an 18 px line height and centered text, replacing a fixed 26 px height that overflowed when a label wrapped
  on a phone. Eleven feed style baselines under `e2e/__baseline__/styles/` were regenerated. A revised design copy
  is kept with the feature. This change was made after the audit and was not audit-verified.

### Notes
- Reservations carried from `web-chat-response-cache`: no red evidence for the handler cache cases, the conventions
  guards and the e2e file (F2); no per-turn hook record and no CI run yet (F3); the audit was done by the implementing
  session (F4); the in-process cache has no size bound or pruning test (F5). `GET` and `SET ... EX` have not been run
  against the real Upstash database; that is part of the human live check.
- Reservations carried from `web-chat-visitor-rate-limit`: the Lua script's expire-on-create and the memory store's
  expiry have no test (F2); `tasks.md` O0 is checked without a pre-change baseline (F3); no CI run of
  `harny-feedback-apps-web.yml` exists for it (F4); its `tasks.md` working state is stale (F5). The live check with a
  real Upstash database (`EVAL` support, shared counts) is a human step.
- Reservations carried: the lint warning in `features/feed/api/types.generated.ts` predates this work; no green
  `harny-feedback-apps-web.yml` run exists yet for this branch.
