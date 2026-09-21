import Link from 'next/link'
import styles from './feed.module.css'
import { feedHref } from './href'
import { topTags } from './tags'
import type { CardOut } from './types.generated'

/** Pinned mockup copy (AD-11) — asserted verbatim, not paraphrased. */
export const CHIP_NOTE = 'Top tags on this page — every tag on a card is clickable.'

export function TagFilter({
  cards,
  activeTag,
}: {
  cards: CardOut[]
  activeTag?: string
}) {
  const chips = topTags(cards)
  const activeTagIsPromoted = activeTag !== undefined && chips.includes(activeTag)
  const displayedTags = activeTag !== undefined && !activeTagIsPromoted
    ? [activeTag, ...chips]
    : chips

  return (
    <div>
      <div className={styles.chipRow}>
        {displayedTags.map((tag) => (
          <Link
            key={tag}
            href={feedHref({ tag })}
            // Distinct accessible name from a card's own inline tag link to
            // the same href — this row is the page-local filter shortcut,
            // not the card's own tag reference.
            aria-label={`Filter by tag ${tag}`}
            className={tag === activeTag ? `${styles.chip} ${styles.chipActive}` : styles.chip}
          >
            {tag}
          </Link>
        ))}
        {activeTag !== undefined ? (
          <Link className={styles.clearLink} href={feedHref({})}>
            All cards
          </Link>
        ) : null}
      </div>
      <p className={styles.chipNote}>{CHIP_NOTE}</p>
    </div>
  )
}
