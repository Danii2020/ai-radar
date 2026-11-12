# Intent: Web Chat Swipe Handle

Shipped: 2026-11-11

Revision: 1
Approval: Approved 2026-11-11 (human accepted the defaults for open questions Q1 to Q7)

## Outcome
On a phone (viewport 640 px wide or less, the existing breakpoint in `features/chat/components/chat.module.css`),
the round "Chat" launcher is replaced by a slim edge tab that peeks from the right edge of the screen in the lower
third of the viewport, with a small chat icon. Swiping left on the tab opens the chat bottom sheet, and tapping it
does too, so the keyboard and screen-reader path stays the same. Swiping right on the open sheet closes it, next to
the existing Close button and Escape. The swipe is threshold-based: it does not follow the finger, and it ignores
mostly-vertical gestures so the page still scrolls. Desktop (wider than 640 px) is unchanged.

## Acceptance criteria

Notation: "phone" is a 375 by 667 viewport; "desktop" is 1280 by 800. A "gesture" is one touch or pen pointer
sequence (down, moves, up) with total travel `dx` (positive = rightward) and `dy` in CSS px. The default thresholds
are **40 px** of horizontal travel with `|dx| >= 2 * |dy|`. Those two numbers are revisable defaults (open question
Q6); the behavior around them is required.

- **AC1** Phone closed state. On a phone with the sheet closed, the launcher (still the one element with
  `data-testid="chat-launcher"`, accessible name "Open chat", `aria-expanded="false"`, `aria-controls` set) is an
  edge tab. Its box is flush with the right viewport edge (right edge within 1 px of the viewport width), 20 to
  24 px wide, at least 44 px tall, and lies entirely in the lower third of the viewport (top at least 2/3 of the
  viewport height, bottom at most the viewport height). It shows an icon (an `aria-hidden` SVG) and no visible
  "Chat" text. The page has no horizontal overflow. Its keyboard focus indicator is visible inside the viewport.
  Colours, spacing and radii come from the design tokens (WEBCHAT-10).
  Example: phone, `/` loaded -> launcher box `x + width` in `[374, 375]`, `width` in `[20, 24]`,
  `y >= 444.67`, `y + height <= 667`; `document.documentElement.scrollWidth <= clientWidth`.

- **AC2** Tap and keyboard open the sheet. On a phone, a tap on the tab, or Enter or Space while it has focus,
  opens the sheet exactly as the launcher does today: the dialog appears, focus moves to the "Your question"
  input, `aria-expanded` is `"true"`, and the tab is hidden while the sheet is open. Every way of closing the sheet
  (Close button, Escape, swipe right) returns focus to the tab.
  Example: phone, focus the tab, press Enter -> dialog visible, input focused; press Escape -> dialog gone, tab
  focused.

- **AC3** Swipe left on the tab opens the sheet. On a phone, a gesture that starts on the tab with
  `dx <= -40` and `|dx| >= 2 * |dy|` opens the sheet once, with focus in the input. The click that a browser may
  fire after that gesture does not close it again.
  Example: touch down on the tab, move by `(-60, +8)`, lift -> dialog open and still open after the trailing
  click; `aria-expanded="true"`.

- **AC4** Non-swipes on the tab do nothing and do not take over the page scroll. On a phone, a gesture that starts
  on the tab and is mostly vertical, rightward, shorter than 40 px horizontally, or cancelled (`pointercancel`)
  does not open the sheet. A vertical drag that starts on the tab still scrolls the page. A mouse drag never opens
  or closes the sheet (a mouse click still toggles it).
  Example: page at the top, touch down on the tab, move the finger up by `(-20, -200)`, lift -> no dialog,
  `window.scrollY` increased.
  Example: move by `(-30, 0)` -> no dialog. Move by `(+60, 0)` -> no dialog.

- **AC5** Swipe right on the open sheet closes it. On a phone, a gesture that starts inside the open sheet with
  `dx >= 40` and `|dx| >= 2 * |dy|` closes the sheet (the default zone is the whole sheet, open question Q3) and
  returns focus to the tab. The conversation is kept: reopening shows the same messages. A gesture that starts in
  the "Your question" textarea, or inside an element that scrolls horizontally (a code block), does not close the
  sheet, so text editing and code scrolling keep working. Vertical scrolling of the conversation still works and
  never closes the sheet. The Close button and Escape still close it.
  Example: sheet open with one answer, touch down on the message area, move by `(+80, +10)`, lift -> dialog gone,
  tab focused; tap the tab -> the answer is still there.
  Example: touch down inside a `pre` block, move by `(+80, 0)` -> dialog still open.

- **AC6** Reduced motion is respected. Any transition or animation this feature adds to the tab or the sheet is
  off under `prefers-reduced-motion: reduce` (computed `transition-duration` `0s` and `animation-name` `none` for
  what it adds), and tap, keyboard and both swipes still work.
  Example: reduced motion, phone -> the tab's computed `transition-duration` is `0s`; swipe left still opens.

- **AC7** (compatibility) Desktop is unchanged. Wider than 640 px, the launcher keeps its look and place (the
  bottom-right pill with "Chat" and "Close" text, a 44 by 44 hit area at least), click toggles it, and no touch,
  pen or mouse drag on the launcher or the panel opens or closes anything (so selecting text in a message by
  dragging still works). The existing desktop tests pass without edits.
  Example: desktop, touch drag `(+80, 0)` on the open panel -> panel still open.

- **AC8** (compatibility) Everything else in `web-chat` and `web-feed` keeps working: the phone sheet layout
  (WEBCHAT-5), the existing chat, layout and rate-limit e2e suites and the 17 feed baseline scenarios pass; the
  barrel `features/chat/index.ts` still exports exactly `ChatWidget` and `handleChatRequest`; no new dependency;
  `chat.module.css` passes the token checker; the page writes nothing to the console. No backend, route or `api/`
  change.

- **AC9** The new behavior is covered offline: unit tests for the gesture rules and the widget, and Playwright at
  the phone viewport with trusted touch input against the existing local stub, with no network call beyond the
  stub and no real credential (WEBCHAT-12).

## Scope
**In**
- Phone-only presentation of the existing launcher as an edge tab with an icon (`chat-widget.tsx`,
  `chat.module.css`).
- Threshold swipe-left on the tab to open, swipe-right on the sheet to close, with pointer events and no new
  dependency.
- Reduced-motion handling for anything this feature animates.
- Tests (unit and e2e) and the `apps/web/AGENTS.md` component note.

**Out**
- Follow-the-finger dragging of the sheet or tab, and a sheet open/close slide animation (default; open question Q4).
- Any desktop change, including touch-screen laptops wider than 640 px.
- A first-visit hint or coachmark for the swipe (open question Q7).
- Backend, `/api/chat` route, `features/chat/api/`, `features/chat/index.ts`, `app/page.tsx` and `globals.css`
  changes; new design tokens.
- WEBCHAT-R9 (`aria-controls` names an unmounted id while closed) stays as it is; this feature does not fix it.
- Real-device verification on Android and iOS is a human step (see Q1), not an executor task.

## Constraints
- **Amends WEBCHAT-1 on phones (stated, not silent).** WEBCHAT-1 says the launcher has a 44 px hit area. On a phone
  the tab is 20 to 24 px wide and at least 44 px tall, which meets the WCAG 2.2 target-size minimum (24 by 24 at
  24 px wide) but not 44 by 44. Desktop keeps 44 by 44. WEBCHAT-1's wording "a floating chat button" also becomes
  "an edge tab" at 640 px and narrower. The human decided this; Q2 asks to confirm the width.
- One launcher element for both widths, so `data-testid="chat-launcher"`, `aria-expanded`, `aria-controls`, the
  accessible names "Open chat" / "Close chat" and the focus-return path stay as they are (WEBCHAT-1).
- Token-only styling (WEBCHAT-10, `chat-css.test.ts`): no hand-authored colour, spacing or radius; sizes and
  positions are layout values. No new token. `globals.css` and `feed.module.css` are not touched (WEB-9).
- No new dependency (AGENTS.md dependency rule); gestures use Pointer Events and CSS `touch-action`.
- `features/chat/lib/`, `api/`, `index.ts` and the route are the stable shell (web-chat invariant 3). This feature
  edits none of the existing files there. It may add one new pure module to `lib/` for the gesture rule
  (suggestion in the plan); that adds to the shell without changing it.
- Gestures only on the phone breakpoint and only from touch or pen pointers, so desktop and mouse behavior is
  unchanged (AC7).
- Tests follow the `high-value-tests` skill; e2e stays offline (WEBCHAT-12).

## Open questions
- **Q1 (needs the human) OS edge gestures.** Android gesture navigation treats a swipe in from the right edge as
  Back, and iOS Safari treats it as Forward when there is forward history. A web page cannot opt out of these
  (Android's gesture-exclusion API is native only). A swipe on a tab flush with the right edge may therefore be
  taken by the OS or browser on some phones. Default: keep the tab flush with the edge as decided, treat tap as the
  guaranteed path and swipe as best effort, record this as a reservation, and have the human check it on a real
  Android (gesture navigation) and iPhone. Alternative: inset the tab a few px from the edge.
- **Q2** Tab width: default 24 px (meets the WCAG 2.2 AA 24 px minimum); allowed range 20 to 24 px. Confirm 24, or
  choose 20 and accept that it is below that minimum.
- **Q3** Swipe-right close zone: default is the whole sheet except the textarea and horizontally scrollable
  elements. Alternative: the sheet header only (fewer accidental closes, smaller target).
- **Q4** Motion: default adds no sheet open/close animation (the sheet mounts and unmounts as today) and at most a
  short press feedback on the tab, which is off under reduced motion. Confirm, or ask for a slide-in.
- **Q5** Icon: default is a small chat-bubble icon. Alternative: a left chevron.
- **Q6** Thresholds: default 40 px horizontal travel and a 2:1 horizontal-to-vertical ratio. Confirm or change.
- **Q7** Discoverability: no first-visit hint by default. Confirm that the tab alone is enough.

## Revision history
- Revision 1 (2026-11-11): first draft from the human's decisions (edge tab on phones, swipe left to open, tap
  opens, swipe right closes, threshold not follow-finger, pointer events, reduced motion, desktop unchanged).
