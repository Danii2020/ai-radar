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
`.github/workflows/harny-feedback-web.yml`.
