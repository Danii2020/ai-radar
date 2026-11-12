# Changelog

All notable changes to `apps/web` are recorded here, in the Keep a Changelog format.

## [Unreleased]

### Added
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
- Reservations carried: the lint warning in `features/feed/api/types.generated.ts` predates this work; no green
  `harny-feedback-apps-web.yml` run exists yet for this branch.
