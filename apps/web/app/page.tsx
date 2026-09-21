import { FeedApiError } from '../features/feed/client'
import { loadFeed } from '../features/feed/load-feed'
import { FeedView, type FeedViewState } from '../features/feed/feed-view'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const params = await searchParams
  const tag = typeof params.tag === 'string' && params.tag.trim() ? params.tag : undefined
  const cursor = typeof params.cursor === 'string' && params.cursor ? params.cursor : undefined

  let state: FeedViewState
  try {
    state = { status: 'ok', page: await loadFeed({ tag, cursor }) }
  } catch (error) {
    // Structured, single-line log — the idiom of src/api/handler.py's
    // `feed_api_request` record. The message never reaches the browser.
    console.error(JSON.stringify({
      event: 'feed_fetch_failed',
      code: error instanceof FeedApiError ? error.code : 'network',
      status: error instanceof FeedApiError ? error.status : undefined,
      tag, has_cursor: cursor !== undefined,
    }))
    state = { status: 'error', code: error instanceof FeedApiError ? error.code : 'network' }
  }

  return <FeedView state={state} tag={tag} cursor={cursor} />
}
