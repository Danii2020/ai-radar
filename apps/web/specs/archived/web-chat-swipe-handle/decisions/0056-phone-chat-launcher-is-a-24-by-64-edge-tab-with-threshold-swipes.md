# ADR 0056: On phones the chat launcher is a 24 by 64 px edge tab with threshold touch and pen swipes

- **Status**: Accepted. Amends WEBCHAT-1 (the 44 px hit area) at 640 px and narrower.
- **Date**: 2026-11-11
- **Feature**: web-chat-swipe-handle
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach (the "phone tab geometry", "restyle the existing button", "gesture rule" and "ADR candidate 0056" bullets); intent.md § Constraints
- **Trigger**: (a) it chooses between named options (restyle the one button or render a second element; edge tab or inset tab; threshold swipe or follow-the-finger); (c) it diverges from WEBCHAT-1's 44 px hit area; (d) it accepts a known cost (the tab is below 44 by 44, and OS edge gestures may take a swipe)

## Context

WEBCHAT-1 set a floating chat button with a 44 px hit area. The human asked for a slimmer phone control: a handle that peeks from the right edge, opens by swiping left and closes by swiping right. A 44 px wide control would cover about 20 px of feed content past the 24 px page gutter. Android gesture navigation and iOS Safari reserve a swipe in from the right edge (Back or Forward), and a web page cannot opt out, so a flush tab may lose some swipes.

## Decision

At 640 px and narrower (the existing breakpoint, shared by the CSS and the gesture code), the one existing launcher button is restyled as an edge tab, 24 px wide and 64 px tall, flush with the right edge in the lower third of the viewport, with an `aria-hidden` icon and no visible text. Tap, Enter and Space open the sheet, a touch or pen swipe left on the tab also opens it, and a swipe right on the open sheet closes it. A swipe is a threshold of 40 px horizontal travel with `|dx| >= 2 * |dy|`, with no follow-the-finger state; mouse input never triggers it. Desktop keeps the 44 by 44 pill. The tab meets WCAG 2.2 AA target size 2.5.8 (24 by 24), and WEBCHAT-1's 44 px rule now applies to desktop only.

## Alternatives considered
| Option | Why not |
|---|---|
| A separate phone-only tab element beside the launcher | Duplicates the test id and splits focus return; three e2e files would need new selectors |
| An invisible 44 px hit area around a 24 px tab | Overlaps about 20 px of card content past the page gutter |
| A tab inset a few px from the right edge | The human chose flush; kept as the fallback if real devices lose too many swipes |
| `touch-action: none` on the tab | Blocks the page scroll that starts on the tab |
| Following the finger, with a sheet slide animation | Out of scope; an exit animation would need a delayed unmount and would fight focus return |
| A gesture library | New dependency; Pointer Events and `touch-action: pan-y` are enough |

## Consequences
**Positive**: the page keeps its full width for the feed, one launcher element keeps every consumer (test id, `aria-*`, focus return) working, and the gesture rule is one pure, unit-tested function.
**Accepted costs**: on phones the control is smaller than 44 by 44. An OS or browser edge swipe may take a swipe-left that starts on the flush tab, so swipe is best effort and tap is the guaranteed path. Real-device checks of the swipe gestures are open (WEBCHAT-R10); the human confirmed on an iPhone (Brave) only that tapping the tab opens the chat. `touch-action: pan-y` on the tab and sheet also stops pinch-zoom that starts there (the audit suggests `pan-y pinch-zoom`).

## Follow-ups
The human checks swipe left and right on an iPhone and on an Android phone with gesture navigation. If the OS takes too many swipes, inset the tab from the edge.
