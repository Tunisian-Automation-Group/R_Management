// When this device last read each conversation, for the Inbox's unread dot
// (UX-12). ponytail: per device; server read receipts replace it with /api/inbox.
const KEY = 'cappy.seen.v1'

function all(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, number>
  } catch {
    return {}
  }
}

export const lastSeen = (bookingId: string): number => all()[bookingId] ?? 0

export function markSeen(bookingId: string, at: string): void {
  const seen = all()
  const ms = Date.parse(at)
  if ((seen[bookingId] ?? 0) >= ms) return
  seen[bookingId] = ms
  try {
    localStorage.setItem(KEY, JSON.stringify(seen))
  } catch {
    // Not remembered: the dot shows again next time, nothing worse.
  }
}
