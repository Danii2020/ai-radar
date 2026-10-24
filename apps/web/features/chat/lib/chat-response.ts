import type { ChatResponse, ChatSource } from '../api/types'

function isSource(value: unknown): value is ChatSource {
  if (typeof value !== 'object' || value === null) return false
  const s = value as Record<string, unknown>
  return (
    typeof s.n === 'number' &&
    typeof s.title === 'string' &&
    typeof s.url === 'string' &&
    typeof s.source === 'string' &&
    (s.published === null || typeof s.published === 'string') &&
    typeof s.score === 'number'
  )
}

/** Boundary shape check for a chat reply (house rule from isCardOut). */
export function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== 'object' || value === null) return false
  const r = value as Record<string, unknown>
  return typeof r.answer === 'string' && Array.isArray(r.sources) && r.sources.every(isSource)
}
