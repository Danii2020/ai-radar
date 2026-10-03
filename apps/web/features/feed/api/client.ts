import type { CardOut, FeedResponse } from './types.generated'

/** Page size requested from feed-api. Its own default is also 20; pinned here
 *  so the drain budget (AD-6) is computable. */
export const PAGE_SIZE = 20
/** Next Data Cache TTL (AD-9). Curation runs daily; 5 min is always fresher. */
export const REVALIDATE_SECONDS = 300
export const FETCH_TIMEOUT_MS = 8_000

/** The artifact's `$defs.CardOut.required`, minus the one numeric field.
 *  A test asserts this list against docs/api/feed-api.v1.schema.json. */
export const REQUIRED_STRING_FIELDS = [
  'card_id', 'title', 'url', 'source', 'summary',
  'type', 'published', 'created_at', 'updated_at',
] as const

export type FeedErrorCode = 'config' | 'network' | 'http' | 'malformed'

export class FeedApiError extends Error {
  readonly code: FeedErrorCode
  readonly status?: number

  constructor(code: FeedErrorCode, message: string, status?: number) {
    super(message)
    this.name = 'FeedApiError'
    this.code = code
    this.status = status
  }
}

export interface FetchFeedParams {
  tag?: string
  /** Opaque token from a previous `next_cursor`. Passed through verbatim. */
  cursor?: string
  limit?: number
}

/** One card page, normalised: `next_cursor` collapsed to `string | null`,
 *  malformed cards dropped and counted (house rule: one bad item never kills
 *  the page — mirrors `query_feed`'s per-item skip in src/api/feed.py). */
export interface FeedPage {
  cards: CardOut[]
  nextCursor: string | null
  /** Cards the API returned that failed `isCardOut` and were dropped. */
  skipped: number
  /** How many HTTP requests produced this page (1, or more after a drain). */
  requests: number
}

/** Runtime shape check at the network boundary. Types are erased at runtime, so
 *  this is what actually protects the render from a contract violation. */
export function isCardOut(value: unknown): value is CardOut {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>

  for (const field of REQUIRED_STRING_FIELDS) {
    if (typeof record[field] !== 'string') return false
  }
  if (typeof record.relevance !== 'number') return false

  return true
}

/** Reads FEED_API_BASE_URL — server-only; never exposed to the browser via a
 *  publicly-inlined env var, and never read from a client-side module. Throws
 *  FeedApiError('config') naming the variable when unset/blank — the
 *  pydantic-settings posture, in TypeScript. */
export function feedApiBaseUrl(): string {
  const value = process.env.FEED_API_BASE_URL

  if (value === undefined || value.trim() === '') {
    throw new FeedApiError('config', 'FEED_API_BASE_URL is not set')
  }

  return value
}

/**
 * Exactly ONE `GET /v1/cards` request. No retry, no loop, no second call.
 * `cursor` is appended verbatim (URL-encoded in transit only).
 * Caching: `{ next: { revalidate: REVALIDATE_SECONDS } }` (AD-9).
 * Throws FeedApiError for config/network/http/malformed; never returns
 * a partially-typed body.
 */
export async function fetchFeed(params: FetchFeedParams = {}): Promise<FeedPage> {
  // May throw FeedApiError('config') — deliberately before any fetch.
  const base = feedApiBaseUrl()

  const url = new URL(`${base}/v1/cards`)
  url.searchParams.set('limit', String(params.limit ?? PAGE_SIZE))
  if (params.tag !== undefined && params.tag.trim() !== '') {
    url.searchParams.set('tag', params.tag)
  }
  if (params.cursor !== undefined && params.cursor !== '') {
    url.searchParams.set('cursor', params.cursor)
  }

  let response: Response
  try {
    response = await fetch(url.toString(), {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
  } catch {
    throw new FeedApiError('network', 'Request to feed-api failed')
  }

  if (!response.ok) {
    throw new FeedApiError(
      'http',
      `feed-api responded with status ${response.status}`,
      response.status,
    )
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new FeedApiError('malformed', 'feed-api response body was not valid JSON')
  }

  if (
    typeof body !== 'object' ||
    body === null ||
    !Array.isArray((body as { cards?: unknown }).cards)
  ) {
    throw new FeedApiError('malformed', 'feed-api response did not match FeedResponse')
  }

  const parsed = body as FeedResponse
  const cards: CardOut[] = []
  let skipped = 0

  for (const item of parsed.cards) {
    if (isCardOut(item)) {
      cards.push(item)
    } else {
      skipped += 1
    }
  }

  const rawNextCursor = parsed.next_cursor
  const nextCursor = typeof rawNextCursor === 'string' && rawNextCursor !== '' ? rawNextCursor : null

  return { cards, nextCursor, skipped, requests: 1 }
}
