import { isIP } from 'node:net'

const HEADERS = ['x-vercel-forwarded-for', 'x-real-ip', 'x-forwarded-for'] as const

function expandIpv6(address: string): number[] | null {
  let text = address.toLowerCase()
  const tail = text.match(/(\d+)\.(\d+)\.(\d+)\.(\d+)$/)
  if (tail) {
    const [a, b, c, d] = tail.slice(1).map(Number)
    text = text.slice(0, tail.index) + ((a << 8) | b).toString(16) + ':' + ((c << 8) | d).toString(16)
  }
  const halves = text.split('::')
  if (halves.length > 2) return null
  const head = halves[0] ? halves[0].split(':') : []
  const rest = halves.length === 2 && halves[1] ? halves[1].split(':') : []
  const fill = 8 - head.length - rest.length
  if (halves.length === 2 ? fill < 1 : fill !== 0) return null
  const groups = [...head, ...Array<string>(halves.length === 2 ? fill : 0).fill('0'), ...rest]
  const parsed = groups.map((g) => (/^[0-9a-f]{1,4}$/.test(g) ? parseInt(g, 16) : NaN))
  return parsed.length === 8 && parsed.every((n) => !Number.isNaN(n)) ? parsed : null
}

/** The canonical visitor key: IPv4 whole, IPv6 reduced to its /64, IPv4-mapped as that IPv4,
 *  anything unusable as the shared `unknown` bucket. Only proxy headers feed it. */
export function visitorKey(headers: Headers): string {
  let raw: string | null = null
  for (const name of HEADERS) {
    const value = headers.get(name)
    if (value !== null) {
      raw = value
      break
    }
  }
  const entry = raw?.split(',')[0].trim() ?? ''
  if (entry === '' || entry.includes('%')) return 'unknown'
  const family = isIP(entry)
  if (family === 4) return entry
  if (family !== 6) return 'unknown'
  const h = expandIpv6(entry)
  if (!h) return 'unknown'
  if (h.slice(0, 5).every((n) => n === 0) && h[5] === 0xffff) {
    return `${h[6] >> 8}.${h[6] & 255}.${h[7] >> 8}.${h[7] & 255}`
  }
  return h.slice(0, 4).map((n) => n.toString(16).padStart(4, '0')).join(':')
}
