import { handleChatRequest } from '@/features/chat'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'
// Above the route's own 30 s backend deadline, so the platform never cuts it first.
export const maxDuration = 40

export function POST(request: Request): Promise<Response> {
  return handleChatRequest(request)
}
