import type { ChatTurn } from '../api/types'
import { HISTORY_MAX_ITEMS, ITEM_MAX_CHARS } from './limits'

/** Alternating {role, text} items, starting with user and (if non-empty) ending with assistant. */
export function isValidHistory(value: unknown): value is ChatTurn[] {
  if (!Array.isArray(value)) return false
  if (value.length % 2 !== 0) return false
  return value.every((item, index) => {
    if (typeof item !== 'object' || item === null) return false
    const { role, text } = item as Record<string, unknown>
    if (typeof text !== 'string') return false
    return role === (index % 2 === 0 ? 'user' : 'assistant')
  })
}

/** Keeps the last HISTORY_MAX_ITEMS items (an even count, so it still starts with user) and
 *  cuts each text to ITEM_MAX_CHARS. Does not mutate its input. */
export function trimHistory(history: ChatTurn[]): ChatTurn[] {
  return history
    .slice(-HISTORY_MAX_ITEMS)
    .map((item) => ({ role: item.role, text: item.text.slice(0, ITEM_MAX_CHARS) }))
}
