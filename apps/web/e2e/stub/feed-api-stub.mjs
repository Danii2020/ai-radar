// Stateless local stand-in for feed-api (`GET <prefix>/v1/cards`), node:http only.
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
  if (tag !== null) {
    return { cards: allCards.filter((c) => (c.tags ?? []).includes(tag)), next_cursor: null }
  }
  if (cursor === null) return { cards: fixtures.page1, next_cursor: fixtures.next_cursor }
  if (cursor === fixtures.next_cursor) return { cards: fixtures.page2, next_cursor: null }
  return { cards: [], next_cursor: null }
}

export function startStub(port = STUB_PORT) {
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://stub.local')
    if (url.pathname === '/health') {
      res.writeHead(200).end('ok')
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
