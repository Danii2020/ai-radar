import { feedHref } from './href'
import styles from './feed.module.css'
import type { CardOut } from './types.generated'

/**
 * The HTML port of `render()` in src/shared/cards.py: title (linking out to
 * card.url, target=_blank rel="noopener noreferrer"), a second visible URL
 * line (also linking to card.url, same target/rel — contract.md's Data
 * Models field-rendering map: url -> "the heading's href + a visible link
 * line", using feed.module.css's `.urlLine` class), summary, bulleted
 * takeaways, clickable tag chips, and a meta line
 * `TYPE · relevance n/10 · source · published`.
 * `tags`/`takeaways` are OPTIONAL in the v1 schema — `undefined` renders as
 * nothing, never as a crash.
 * The root element carries `data-type={card.type}` — feed.module.css's
 * `.card[data-type="…"]` selectors (AD-7) apply the accent colour; this
 * component performs no colour lookup of its own, and an unrecognised type
 * simply matches no selector (neutral fallback, by CSS default).
 */
export function CardItem({ card }: { card: CardOut }) {
  const tags = card.tags ?? []
  const takeaways = card.takeaways ?? []
  const publishedText = card.published === '' ? 'date n/a' : card.published

  return (
    <article className={styles.card} data-type={card.type}>
      <h2 className={styles.cardTitle}>
        <a
          className={styles.cardTitleLink}
          href={card.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {card.title}
        </a>
      </h2>
      <a
        className={styles.urlLine}
        href={card.url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {card.url}
      </a>
      <p className={styles.summary}>{card.summary}</p>
      {takeaways.length > 0 ? (
        <ul className={styles.takeaways}>
          {takeaways.map((takeaway, index) => (
            <li key={index}>{takeaway}</li>
          ))}
        </ul>
      ) : null}
      {tags.length > 0 ? (
        <div className={styles.cardTags}>
          {tags.map((tag) => (
            <a key={tag} className={styles.chip} href={feedHref({ tag })}>
              {tag}
            </a>
          ))}
        </div>
      ) : null}
      <div className={styles.cardFoot}>
        <span className={styles.badge}>{card.type}</span>
        <p className={styles.meta}>
          {card.type}
          <span className={styles.metaSep}>·</span>
          {`relevance ${card.relevance}/10`}
          <span className={styles.metaSep}>·</span>
          {card.source}
          <span className={styles.metaSep}>·</span>
          <time dateTime={card.published || undefined}>{publishedText}</time>
        </p>
      </div>
    </article>
  )
}
