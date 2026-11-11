import Link from 'next/link'
import styles from './feed.module.css'
import { feedHref } from '../lib/href'

export function Pagination({
  tag,
  cursor,
  nextCursor,
  prevCursor,
}: {
  tag?: string
  cursor?: string
  nextCursor: string | null
  prevCursor: string | null
}) {
  const hasFirstPageLink = Boolean(cursor)
  const hasPrevPageLink = prevCursor !== null
  const hasNextPageLink = nextCursor !== null

  if (!hasFirstPageLink && !hasPrevPageLink && !hasNextPageLink) {
    return null
  }

  return (
    <div className={styles.pagerBar}>
      {hasFirstPageLink ? (
        <Link className={styles.pagerLink} href={feedHref({ tag })}>
          ← First page
        </Link>
      ) : (
        <span />
      )}
      {hasPrevPageLink ? (
        <Link
          className={styles.pagerLink}
          href={feedHref({ tag, cursor: prevCursor, direction: 'prev' })}
        >
          ‹ Previous page
        </Link>
      ) : null}
      {hasNextPageLink ? (
        <Link className={styles.pagerLink} href={feedHref({ tag, cursor: nextCursor })}>
          Next page →
        </Link>
      ) : null}
    </div>
  )
}
