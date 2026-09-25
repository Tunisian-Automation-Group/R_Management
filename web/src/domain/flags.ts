/**
 * Percentage rollouts (S-26). The server sends `rollouts: {name: percent}` in
 * app-config, the same answer for everyone so the CDN can cache it; each app
 * places its own user. Must match the server's contract exactly:
 * FNV-1a 32 over the UTF-8 of `name:userId`, mod 100, in when below percent.
 */
export function bucket(name: string, userId: string): number {
  let h = 0x811c9dc5
  for (const b of new TextEncoder().encode(`${name}:${userId}`)) {
    h ^= b
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h % 100
}

export function flagOn(
  name: string,
  config: { flags?: Record<string, boolean>; rollouts?: Record<string, number> } | undefined,
  userId: string | undefined,
): boolean {
  if (config?.flags?.[name]) return true
  const percent = config?.rollouts?.[name]
  return percent !== undefined && userId !== undefined && bucket(name, userId) < percent
}
