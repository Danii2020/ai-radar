import { fetchFeed, type FeedPage } from './client'

/** Bounded so a pathological filter cannot fan one page view into unbounded
 *  billed requests (AD-6). 5 x PAGE_SIZE(20) = 100 > the 87-card corpus. */
export const MAX_DRAIN_REQUESTS = 5

export interface LoadFeedParams {
  tag?: string
  cursor?: string
}

/**
 * `fetchFeed`, plus Spec 01 Guarantee 4 handling: while the page came back
 * EMPTY and `nextCursor` is non-null, follow the cursor — up to
 * MAX_DRAIN_REQUESTS requests in total. Returns the first non-empty page, or
 * the last empty one (with its cursor intact, so the UI can still offer "next
 * page" and must not claim "no matches" for pages it never read).
 *
 * A non-empty short page is returned immediately: shortness is normal and is
 * never drained.
 */
export async function loadFeed(params: LoadFeedParams = {}): Promise<FeedPage> {
  let cursor = params.cursor
  let page = await fetchFeed({ tag: params.tag, cursor })
  let requests = 1

  while (
    page.cards.length === 0 &&
    page.nextCursor !== null &&
    requests < MAX_DRAIN_REQUESTS
  ) {
    cursor = page.nextCursor
    page = await fetchFeed({ tag: params.tag, cursor })
    requests += 1
  }

  return { ...page, requests }
}
