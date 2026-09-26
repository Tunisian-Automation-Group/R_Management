/**
 * One Idempotency-Key per attempt at the same request (FL-1). The key follows
 * the exact body: a retry after a 503, 502, 504, timeout or lost connection
 * reuses it, so the server replays what it may already have done (a booking
 * kept in awaiting_payment) instead of colliding with it. A new key only
 * after a success, a definite 4xx, or a different body (another slot, an
 * edited text), since the same key with another body is refused.
 */
export function attemptKeys(newKey: () => string = () => crypto.randomUUID()) {
  let last: { key: string; body: string } | null = null
  return {
    /** The key to send with `body`. */
    keyFor(body: unknown): string {
      const b = JSON.stringify(body)
      if (last?.body !== b) last = { key: newKey(), body: b }
      return last.key
    },
    /** After the call: pass the error if it failed. */
    settle(err?: unknown): void {
      if (err === undefined || definite(err)) last = null
    },
  }
}

/** The server answered, and it will answer the same again: a 4xx. A 5xx, a
 *  timeout or no answer at all (status 0) may mean it did the thing and
 *  could not say so. */
export const definite = (err: unknown): boolean => {
  const status = (err as { status?: unknown } | null)?.status
  return typeof status === 'number' && status >= 400 && status < 500
}
