# ADR 0038: Assistant markdown renders through a safe subset

- **Status**: Accepted
- **Date**: 2026-10-24
- **Feature**: web-chat-ui-polish
- **Capability**: web-chat
- **Source**: execution-plan.md § Proposed approach 4
- **Trigger**: (a) a choice between named options, and (b) it constrains future features (no raw-HTML plugin, no `dangerouslySetInnerHTML`)

## Context
Assistant answers are model-written text built from card content, so they must be treated as untrusted. They need bold, lists and code to read well.

## Decision
`MessageResponse` renders `react-markdown` with an `allowedElements` list (`p`, `strong`, `em`, `ol`, `ul`, `li`, `a`, `code`, `pre`, `blockquote`, `br`, `hr`, `h1` to `h6`) and `unwrapDisallowed`, which drops `img` and keeps the text of anything else. A `urlTransform` returns a URL only for `http:` and `https:`. The `a` override adds `target="_blank"` and `rel="noopener noreferrer"`, and renders a plain `<span>` when the href is empty. Default raw-HTML handling stays, so HTML shows as inert visible text. There is no `rehype-raw` and no `dangerouslySetInnerHTML`. User messages stay plain text.

## Alternatives considered
| Option | Why not |
|---|---|
| `defaultUrlTransform` | It also allows `mailto`, `irc`, `ircs`, `xmpp` and relative links, which point at our own origin. |
| `skipHtml` | It hides what the model wrote with no trace; either choice is safe. |

## Consequences
**Positive**: the audit checked 25 adversarial inputs and no script, image or non-http(s) href was produced.
**Accepted costs**: no images, tables or autolinks. The audit's open finding F8 notes that source links use `source.url` unfiltered and that an image inside a link renders an `<a>` with no accessible name.

## Follow-ups
Optionally filter `source.url` to http(s) and keep image alt text as text (F8).
