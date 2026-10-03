import type { FeedViewState } from '../components/feed-view'
import { FeedApiError } from './client'
import { loadFeed } from './load-feed'

export async function loadFeedState({
  tag,
  cursor,
}: {
  tag?: string
  cursor?: string
}): Promise<FeedViewState> {
  try {
    return { status: 'ok', page: await loadFeed({ tag, cursor }) }
  } catch (error) {
    // Structured, single-line log — the idiom of src/api/handler.py's
    // `feed_api_request` record. The message never reaches the browser.
    console.error(JSON.stringify({
      event: 'feed_fetch_failed',
      code: error instanceof FeedApiError ? error.code : 'network',
      status: error instanceof FeedApiError ? error.status : undefined,
      tag, has_cursor: cursor !== undefined,
    }))
    return { status: 'error', code: error instanceof FeedApiError ? error.code : 'network' }
  }
}
