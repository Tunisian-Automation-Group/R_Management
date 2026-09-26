// The release guard (R2-1), apart from the Vite config so a plain node check
// can test it (R2-21: scripts/check-release.ts).
/**
 * A release build (VITE_RELEASE=1, set by the deploy) refuses to build
 * without what the law and the stores need on screen: the operator's
 * company, address and contact (Impressum, privacy, DSA contact point), and
 * well-formed app-link values when given. Local and CI builds leave it unset.
 */
export function releaseProblems(env: Record<string, string | undefined>): string[] {
  if (env.VITE_RELEASE !== '1') return []
  const problems: string[] = []
  for (const key of ['VITE_LEGAL_COMPANY', 'VITE_LEGAL_ADDRESS', 'VITE_LEGAL_EMAIL']) {
    if (!env[key]?.trim()) problems.push(`${key} is empty`)
  }
  const email = env.VITE_LEGAL_EMAIL?.trim()
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) problems.push('VITE_LEGAL_EMAIL is not an email address')
  const sha = env.VITE_ANDROID_SHA256?.trim()
  if (sha && (!/^([0-9A-F]{2}:){31}[0-9A-F]{2}$/i.test(sha) || /^(00:){31}00$/.test(sha))) {
    problems.push('VITE_ANDROID_SHA256 is not a real SHA-256 fingerprint (32 colon-separated hex bytes)')
  }
  const team = env.VITE_APPLE_TEAM_ID?.trim()
  if (team && !/^[A-Z0-9]{10}$/.test(team)) problems.push('VITE_APPLE_TEAM_ID is not a 10-character team id')
  return problems
}
