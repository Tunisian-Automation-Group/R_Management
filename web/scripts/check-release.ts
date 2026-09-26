// The release guard refuses what must never ship (R2-21): no operator
// identity, a malformed contact, a placeholder app-link fingerprint.
// Run: npm run check:release
import assert from 'node:assert/strict'
import { releaseProblems } from '../release.ts'

const sha = Array.from({ length: 32 }, (_, i) => i.toString(16).padStart(2, '0').toUpperCase()).join(':')
const good = {
  VITE_RELEASE: '1',
  VITE_LEGAL_COMPANY: 'Cappy GmbH',
  VITE_LEGAL_ADDRESS: 'Teststraße 1, 10115 Berlin',
  VITE_LEGAL_EMAIL: 'hello@cappy.app',
  VITE_ANDROID_SHA256: sha,
  VITE_APPLE_TEAM_ID: 'ABCDE12345',
}
assert.deepEqual(releaseProblems(good), [], 'good values pass')
assert.deepEqual(releaseProblems({}), [], 'only release builds are checked')
for (const key of ['VITE_LEGAL_COMPANY', 'VITE_LEGAL_ADDRESS', 'VITE_LEGAL_EMAIL']) {
  assert.ok(releaseProblems({ ...good, [key]: '' }).some((p) => p.startsWith(key)), `${key} empty is refused`)
  assert.ok(releaseProblems({ ...good, [key]: '   ' }).length, `${key} blank is refused`)
}
assert.ok(releaseProblems({ ...good, VITE_LEGAL_EMAIL: 'not-an-email' }).length, 'a malformed email is refused')
const zero = Array(32).fill('00').join(':')
assert.ok(releaseProblems({ ...good, VITE_ANDROID_SHA256: zero }).length, 'the all-zero fingerprint is refused')
assert.ok(releaseProblems({ ...good, VITE_ANDROID_SHA256: 'AB:CD' }).length, 'a short fingerprint is refused')
assert.ok(releaseProblems({ ...good, VITE_APPLE_TEAM_ID: 'short' }).length, 'a malformed team id is refused')
assert.deepEqual(releaseProblems({ ...good, VITE_ANDROID_SHA256: '', VITE_APPLE_TEAM_ID: '' }), [], 'app ids are optional')
console.log('release: the guard refuses a build without operator identity or with placeholder app links')
