import type { ChatErrorCode, ChatSource, ChatTurn } from '../api/types'

export interface Message {
  role: 'user' | 'assistant'
  text: string
  sources?: ChatSource[]
}

export interface ConversationState {
  /** Completed turns only. */
  messages: Message[]
  /** The in-flight question, or null. */
  pending: string | null
  error: ChatErrorCode | null
}

export type ConversationAction =
  | { type: 'asked'; question: string }
  | { type: 'answered'; answer: string; sources: ChatSource[] }
  | { type: 'failed'; code: ChatErrorCode }

export const initialConversation: ConversationState = { messages: [], pending: null, error: null }

export function conversationReducer(state: ConversationState, action: ConversationAction): ConversationState {
  switch (action.type) {
    case 'asked':
      return { ...state, pending: action.question, error: null }
    case 'answered':
      if (state.pending === null) return state
      return {
        messages: [
          ...state.messages,
          { role: 'user', text: state.pending },
          { role: 'assistant', text: action.answer, sources: action.sources },
        ],
        pending: null,
        error: null,
      }
    case 'failed':
      return { ...state, pending: null, error: action.code }
  }
}

/** Completed turns, as sent in `history`: no sources. */
export function selectHistory(state: ConversationState): ChatTurn[] {
  return state.messages.map(({ role, text }) => ({ role, text }))
}
