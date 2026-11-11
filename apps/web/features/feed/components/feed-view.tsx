import Link from 'next/link'
import { CardItem } from './card-item'
import type { FeedErrorCode, FeedPage } from '../api/client'
import styles from './feed.module.css'
import { feedHref } from '../lib/href'
import { Pagination } from './pagination'
import { TagFilter } from './tag-filter'

/** Static masthead copy (AD-13) — exported so feed-view.test.tsx can assert
 *  presence without hard-coding the strings in the test. */
export const WORDMARK = 'AI RADAR'
export const TAGLINE = 'curated AI news'

export type FeedViewState =
  | { status: 'ok'; page: FeedPage }
  | { status: 'error'; code: FeedErrorCode }

export interface FeedViewProps {
  state: FeedViewState
  /** The active tag filter, or undefined for the unfiltered feed. */
  tag?: string
  /** The cursor this page was rendered from (undefined on the first page). */
  cursor?: string
  /** `'prev'` when the request came from a Previous link (`dir=prev`). */
  direction?: 'prev'
}

const ERROR_BODY_BY_CODE: Record<FeedErrorCode, string> = {
  config: 'The feed could not be loaded because of a configuration problem.',
  network: "We couldn't reach the feed service. Please try again in a moment.",
  http: 'The feed service returned an unexpected response.',
  malformed: 'The feed service sent data we could not understand.',
}

function Masthead() {
  return (
    <header className={styles.masthead}>
      <span className={styles.wordmark}>{WORDMARK}</span>
      <span className={styles.tagline}>{TAGLINE}</span>
    </header>
  )
}

function FeedList({ page, tag, cursor }: { page: FeedPage; tag?: string; cursor?: string }) {
  return (
    <div data-testid="feed-list">
      <TagFilter cards={page.cards} activeTag={tag} />
      <Pagination tag={tag} cursor={cursor} nextCursor={page.nextCursor} prevCursor={page.prevCursor} />
      <ul className={styles.feedList}>
        {page.cards.map((card) => (
          <li key={card.card_id}>
            <CardItem card={card} />
          </li>
        ))}
      </ul>
      <Pagination tag={tag} cursor={cursor} nextCursor={page.nextCursor} prevCursor={page.prevCursor} />
    </div>
  )
}

function FeedEmpty() {
  return (
    <div data-testid="feed-empty" className={styles.state}>
      <h2 className={styles.stateHeading}>No cards yet</h2>
      <p className={styles.stateBody}>
        No cards yet — the curation run hasn&apos;t produced any.
      </p>
    </div>
  )
}

function FeedNoMatch({
  page,
  tag,
  cursor,
  direction,
}: {
  page: FeedPage
  tag?: string
  cursor?: string
  direction?: 'prev'
}) {
  // Guarantee 7: a live cursor in the drained direction means the drain cap
  // was reached, not that the search is complete — the copy (and the page
  // link) must stay honest about having read only the first N pages.
  const backward = direction === 'prev'
  const drained = (backward ? page.prevCursor : page.nextCursor) !== null
  const pageWord = page.requests === 1 ? 'page' : 'pages'

  let heading: string
  let body: string
  if (backward) {
    heading = drained ? 'No earlier matches found yet' : 'No earlier matches'
    body = drained
      ? `We searched ${page.requests} ${pageWord} back${
          tag ? ` for “${tag}”` : ''
        } and found no matches. More may exist further back — use the previous page link below.`
      : `There are no earlier cards${tag ? ` tagged “${tag}”` : ''}. Use the next page link below.`
  } else {
    heading = drained
      ? 'No matches found yet'
      : tag
        ? `No cards tagged “${tag}”`
        : 'No cards on this page'
    body = drained
      ? `We searched the first ${page.requests} ${pageWord} of the feed${
          tag ? ` for “${tag}”` : ''
        } and found no matches. More may exist further in — use the next page link below.`
      : tag
        ? `No cards are tagged “${tag}” right now.`
        : 'There are no cards on this page. Use the page links below.'
  }

  return (
    <div data-testid="feed-no-match">
      <TagFilter cards={page.cards} activeTag={tag} />
      <div className={styles.state}>
        <h2 className={styles.stateHeading}>{heading}</h2>
        <p className={styles.stateBody}>{body}</p>
      </div>
      <Pagination
        tag={tag}
        cursor={cursor}
        nextCursor={page.nextCursor}
        prevCursor={page.prevCursor}
      />
    </div>
  )
}

function FeedError({
  code,
  tag,
  cursor,
  direction,
}: {
  code: FeedErrorCode
  tag?: string
  cursor?: string
  direction?: 'prev'
}) {
  const retryHref = feedHref({ tag, cursor, direction })
  const firstPageHref = feedHref({ tag })
  const showFirstPageLink = code === 'http' && Boolean(cursor)

  return (
    <div data-testid="feed-error" className={`${styles.state} ${styles.stateError}`}>
      <h2 className={styles.stateHeading}>The feed is temporarily unavailable.</h2>
      <p className={styles.stateBody}>{ERROR_BODY_BY_CODE[code]}</p>
      <div className={styles.stateActions}>
        <Link className={styles.pagerLink} href={retryHref}>
          Try again
        </Link>
        {showFirstPageLink ? (
          <Link className={styles.pagerLink} href={firstPageHref}>
            Back to the first page
          </Link>
        ) : null}
      </div>
    </div>
  )
}

/**
 * Renders the static masthead (AD-13; `.masthead`/`.wordmark`/`.tagline` from
 * feed.module.css), then exactly one of four things, each with a stable
 * `data-testid`:
 *   'feed-list'      — one or more cards (in API order; never re-sorted)
 *   'feed-empty'     — no cards, no tag, cursor exhausted  ("no cards yet")
 *   'feed-no-match'  — no cards, a tag is active           ("no cards tagged X")
 *   'feed-error'     — state.status === 'error'
 * The masthead renders identically across all four states. Pagination and the
 * tag chip row render alongside 'feed-list'/'feed-no-match' whenever a next
 * cursor exists.
 */
export function FeedView({ state, tag, cursor, direction }: FeedViewProps) {
  return (
    <div className={styles.feedPage}>
      <Masthead />
      {state.status === 'error' ? (
        <FeedError code={state.code} tag={tag} cursor={cursor} direction={direction} />
      ) : state.page.cards.length > 0 ? (
        <FeedList page={state.page} tag={tag} cursor={cursor} />
      ) : tag !== undefined || state.page.nextCursor !== null || state.page.prevCursor !== null ? (
        <FeedNoMatch page={state.page} tag={tag} cursor={cursor} direction={direction} />
      ) : (
        <FeedEmpty />
      )}
    </div>
  )
}
