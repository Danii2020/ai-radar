# ai-radar-web

The AI Radar web feed — Next.js (App Router) app, `npm`-managed, deployed on
Vercel. This is Phase 2 ("web feed") of the AI Radar project.

For local-dev setup, the toolchain commands, the manual Vercel deploy
runbook, and the `feed-api` CORS follow-up, see the repo root
[`README.md`](../../README.md) — that is the single source of truth for this
app's runbook; it is not duplicated here.

## SDD harness

This app has its own [harny](https://github.com/Danii2020/harny) SDD harness,
separate from the repo root's Python one: `.sdd/` (`stack: typescript`),
`.claude/{agents,skills,settings.json}`, `.mcp.json`, and its own knowledge
base at [`specs/current/_index.md`](specs/current/_index.md). Launch `claude`
from **this directory** for frontend work so the eslint + tsc per-turn hook
and these agents/skills apply. CI runs the same checks via the root
`.github/workflows/harny-feedback-apps-web.yml`.

## Chat widget: local setup

The feed page mounts a floating chat button. The browser only calls the same-origin
`POST /api/chat`; that Node.js route signs each turn with AWS SigV4 and relays it to the
deployed `POST /v1/chat` API. Copy the three `CHAT_API_*` placeholders from `.env.example` into
`.env.local` (gitignored): `CHAT_API_BASE_URL`, `CHAT_API_ACCESS_KEY_ID`,
`CHAT_API_SECRET_ACCESS_KEY`. They are server-only (never `NEXT_PUBLIC_`).

Putting the real key there is a human step: read it yourself from the local AWS profile
`ai-radar-chat-caller`, and never paste it into a chat, a log or the repo. Then run
`npm run dev`, open the page, ask one question, and check that the answer cites `[1]` (the live
check, WEBCHAT-R2). Without the variables the widget shows its "unavailable" state. Tests and
`npm run test:e2e` use fake credentials and a local stub, and need no AWS access. Key rotation
and the leak response are in the root README, "Authentication amendment (`chat-api-auth`)".

The widget UI (`web-chat-ui-polish`): assistant answers render as markdown through `react-markdown`
(a safe subset: no raw HTML, no images, http(s) links only), the conversation follows the newest
message with `use-stick-to-bottom` (a "Jump to latest" button appears when you scroll away), and on
a phone (640 px and narrower) the panel is a full-width bottom sheet. Both packages are pinned
exactly; see `AGENTS.md`. Overflow, scrolling and reduced-motion checks live in `e2e/layout.e2e.ts`
and `e2e/chat.e2e.ts`, because jsdom has no layout engine.
