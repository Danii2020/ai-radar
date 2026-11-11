export interface FeedHrefParams {
  tag?: string | null
  cursor?: string | null
  /** Web-only hint for a backward request; never forwarded to feed-api. */
  direction?: 'prev'
}

/** `/` , `/?tag=agents`, `/?tag=agents&cursor=<encoded>`. Empty/nullish values
 *  are omitted entirely (never `?tag=`). The cursor value is passed through
 *  URLSearchParams untouched — encoded for transit, identical in value. */
export function feedHref(params: FeedHrefParams = {}): string {
  const search = new URLSearchParams()

  if (params.tag) {
    search.set('tag', params.tag)
  }
  if (params.cursor) {
    search.set('cursor', params.cursor)
    if (params.direction === 'prev') {
      search.set('dir', 'prev')
    }
  }

  const query = search.toString()
  return query ? `/?${query}` : '/'
}
