// Stateless local stand-in for feed-api (`GET <prefix>/v1/cards`) and the chat API
// (`POST <prefix>/v1/chat`), node:http only.
// Every response is a pure function of (prefix, tag, cursor): no state, so the
// Next Data Cache cannot make scenarios interfere. Never contacts the network.
import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const STUB_PORT = 4010
const fixtures = JSON.parse(
  readFileSync(fileURLToPath(new URL('../fixtures/populated.json', import.meta.url)), 'utf-8'),
)
const allCards = [...fixtures.page1, ...fixtures.page2, ...fixtures.late]

const LONG_URL = `https://example.invalid/${'a'.repeat(300 - 'https://example.invalid/'.length)}`

function respond(prefix, tag, cursor) {
  if (prefix === '/empty') return { cards: [], next_cursor: null }
  if (prefix !== '/populated') return undefined

  if (tag === 'drain') {
    const n = cursor && cursor.startsWith('drain-') ? Number(cursor.slice(6)) : 0
    return { cards: [], next_cursor: `drain-${n + 1}` }
  }
  if (tag === 'late') {
    return cursor === 'late-1'
      ? { cards: fixtures.late, next_cursor: null }
      : { cards: [], next_cursor: 'late-1' }
  }
  if (tag === 'long-url') {
    // One card whose URL is 300 characters with no break points (layout e2e only; no baseline uses this tag).
    return { cards: [{ ...fixtures.page1[0], url: LONG_URL }], next_cursor: null }
  }
  if (tag !== null) {
    return { cards: allCards.filter((c) => (c.tags ?? []).includes(tag)), next_cursor: null }
  }
  if (cursor === null) return { cards: fixtures.page1, next_cursor: fixtures.next_cursor }
  if (cursor === fixtures.next_cursor) return { cards: fixtures.page2, next_cursor: null }
  return { cards: [], next_cursor: null }
}

// Chat stand-in. A request without a SigV4 Authorization header scoped to
// us-east-1/execute-api/aws4_request gets 403, so a signing bug shows up as a failed turn.
// The reply is chosen by a keyword in the question: throttle -> 429, timeout -> 504,
// broken -> 502, forbidden -> 403, markdown / longurl / unsafe / tall -> special answers, slow -> the tall
// answer after 1.5 s, anything else -> an answer with 3 sources.
const SIGV4_SCOPE = /^AWS4-HMAC-SHA256 Credential=[^/\s,]+\/\d{8}\/us-east-1\/execute-api\/aws4_request,/
const CHAT_SOURCES = [1, 2, 3].map((n) => ({
  n,
  title: `Stub source ${n}`,
  url: `https://example.test/source-${n}`,
  source: `Stub Wire ${n}`,
  published: '2026-10-20',
  score: 1 - n / 10,
}))

const PARAGRAPH =
  'Agent frameworks keep converging on the same shape: a planner, a set of tools and a memory layer that survives restarts.'
const TALL_ANSWER = `${[1, 2, 3, 4, 5, 6].map((n) => `Paragraph ${n}. ${PARAGRAPH} ${PARAGRAPH}`).join('\n\n')} [1]`
const MARKDOWN_ANSWER = [
  '**Agents** matter:',
  '',
  '1. LangGraph [1]',
  '2. CrewAI [2]',
  '',
  '- inline `code` here',
  '- another bullet',
  '',
  '```',
  'const agent = build()',
  '```',
].join('\n')
const LONGURL_ANSWER = `See [the long link](${LONG_URL}) [1].\n\n\`\`\`\n${LONG_URL}\n\`\`\``
const UNSAFE_ANSWER = [
  '<script>alert(1)</script>',
  '[x](javascript:alert(1))',
  '<img src=x onerror=alert(1)>',
  '![t](https://example.test/p.png)',
  '[d](data:text/html,hi)',
  '[ok](https://example.test/ok)',
].join('\n\n')

function chatReply(req, rawBody) {
  if (!SIGV4_SCOPE.test(req.headers.authorization ?? '')) return [403, { message: 'Forbidden' }]
  let question = ''
  try {
    question = String(JSON.parse(rawBody).question ?? '')
  } catch {
    return [400, { error: 'invalid_request', detail: 'bad json' }]
  }
  if (question.includes('throttle')) return [429, { message: 'Too Many Requests' }]
  if (question.includes('timeout')) return [504, { error: 'upstream_timeout' }]
  if (question.includes('broken')) return [502, { error: 'upstream_failure' }]
  if (question.includes('forbidden')) return [403, { message: 'Forbidden' }]
  if (question.includes('markdown')) return [200, { answer: MARKDOWN_ANSWER, sources: CHAT_SOURCES }]
  if (question.includes('longurl')) {
    return [200, { answer: LONGURL_ANSWER, sources: [{ ...CHAT_SOURCES[0], title: 'Long source', url: LONG_URL }] }]
  }
  if (question.includes('unsafe')) return [200, { answer: UNSAFE_ANSWER, sources: [] }]
  if (question.includes('tall')) return [200, { answer: TALL_ANSWER, sources: [] }]
  if (question.includes('slow')) return [200, { answer: TALL_ANSWER, sources: [] }, 1500]
  return [200, { answer: 'Stub answer: agent frameworks keep converging [1] [2] [3].', sources: CHAT_SOURCES }]
}

export function startStub(port = STUB_PORT) {
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://stub.local')
    if (url.pathname === '/health') {
      res.writeHead(200).end('ok')
      return
    }
    if (req.method === 'POST' && /^\/[a-z]+\/v1\/chat$/.test(url.pathname)) {
      let raw = ''
      req.on('data', (chunk) => (raw += chunk))
      req.on('end', () => {
        const [status, body, delayMs = 0] = chatReply(req, raw)
        setTimeout(() => {
          res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify(body))
        }, delayMs)
      })
      return
    }
    const match = /^(\/[a-z]+)\/v1\/cards$/.exec(url.pathname)
    const tag = url.searchParams.get('tag')
    if (tag === 'network') {
      req.socket.destroy()
      return
    }
    if (tag === 'http-500') {
      res.writeHead(500, { 'content-type': 'application/json' }).end('{"error":"boom"}')
      return
    }
    if (tag === 'malformed') {
      res.writeHead(200, { 'content-type': 'application/json' }).end('<<not json')
      return
    }
    const body = match ? respond(match[1], tag, url.searchParams.get('cursor')) : undefined
    if (body === undefined) {
      res.writeHead(404).end('not found')
      return
    }
    res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify(body))
  })
  server.listen(port, '127.0.0.1')
  return server
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  startStub()
}
