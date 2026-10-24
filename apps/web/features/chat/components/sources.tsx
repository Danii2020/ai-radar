import { useId, useState } from 'react'
import type { ChatSource } from '../api/types'
import styles from './chat.module.css'

export function Sources({ sources }: { sources: ChatSource[] }) {
  const listId = useId()
  const [expanded, setExpanded] = useState(false)
  if (sources.length === 0) return null
  return (
    <div className={styles.sources}>
      <button
        type="button"
        className={styles.sourcesToggle}
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => setExpanded((value) => !value)}
      >
        Sources ({sources.length})
      </button>
      {expanded ? (
        <ol id={listId} className={styles.sourceList}>
          {sources.map((source) => (
            <Source key={source.n} source={source} />
          ))}
        </ol>
      ) : null}
    </div>
  )
}

export function Source({ source }: { source: ChatSource }) {
  return (
    <li>
      <a href={source.url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>
        <span>[{source.n}]</span> {source.title} <span className={styles.sourceName}>{source.source}</span>
      </a>
    </li>
  )
}
