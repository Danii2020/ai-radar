import styles from './chat.module.css'

export const GREETING = 'Hi, I can answer questions about the AI news cards on this page, with sources.'

export const SUGGESTIONS = [
  'What are the most important AI stories right now?',
  'Which new AI models or tools were released recently?',
  'What is the latest research on AI agents?',
]

export function ConversationEmptyState({ onSuggest }: { onSuggest: (question: string) => void }) {
  return (
    <div className={styles.empty}>
      <p className={styles.greeting}>{GREETING}</p>
      <div className={styles.suggestions}>
        {SUGGESTIONS.map((question) => (
          <button key={question} type="button" className={styles.suggestion} onClick={() => onSuggest(question)}>
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}
