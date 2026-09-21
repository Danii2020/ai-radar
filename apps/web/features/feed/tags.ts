import type { CardOut } from './types.generated'

export const MAX_TAG_CHIPS = 12

/** The most frequent tags among `cards`, descending by count, ties broken
 *  alphabetically (deterministic → testable). Cards with `tags === undefined`
 *  contribute nothing. Never invents a global vocabulary — there is no /tags
 *  endpoint (AD-11).
 *
 *  Deliberately hand-rolled selection instead of the array-prototype ordering
 *  method (features/feed's convention guard forbids it) — fine at this scale
 *  (a page's worth of distinct tags, never the full 281-tag corpus). */
export function topTags(cards: CardOut[], limit: number = MAX_TAG_CHIPS): string[] {
  const counts = new Map<string, number>()

  for (const card of cards) {
    for (const tag of card.tags ?? []) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
  }

  const remaining = Array.from(counts.entries())
  const ordered: string[] = []

  while (remaining.length > 0 && ordered.length < limit) {
    let bestIndex = 0
    for (let i = 1; i < remaining.length; i += 1) {
      const [tag, count] = remaining[i]
      const [bestTag, bestCount] = remaining[bestIndex]
      if (count > bestCount || (count === bestCount && tag < bestTag)) {
        bestIndex = i
      }
    }
    ordered.push(remaining[bestIndex][0])
    remaining.splice(bestIndex, 1)
  }

  return ordered
}
