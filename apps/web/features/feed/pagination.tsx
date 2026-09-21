import Link from 'next/link'
import styles from './feed.module.css'
import { feedHref } from './href'

export function Pagination({
  tag,
  cursor,
  nextCursor,
}: {
  tag?: string
  cursor?: string
  nextCursor: string | null
}) {
  const hasFirstPageLink = Boolean(cursor)
  const hasNextPageLink = nextCursor !== null

  if (!hasFirstPageLink && !hasNextPageLink) {
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
      {hasNextPageLink ? (
        <Link className={styles.pagerLink} href={feedHref({ tag, cursor: nextCursor })}>
          Next page →
        </Link>
      ) : null}
    </div>
  )
}
