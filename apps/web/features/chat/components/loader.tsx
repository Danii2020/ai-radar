import styles from './chat.module.css'

export function Loader() {
  return (
    <div role="status" className={styles.loader}>
      <span className={styles.dots} aria-hidden="true">
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.dot} />
      </span>
      <span className={styles.srOnly}>Thinking</span>
    </div>
  )
}
