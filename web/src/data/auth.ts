// Signing in: the session, where its tokens live, and how tabs and devices
// follow it. The identity service itself sits behind an `AuthProvider`
// (./cognito.ts, F-2): Cognito today, anything that issues access tokens the
// services can verify tomorrow.
//
// Tokens: the access token (sent to /api) and the id token (who this is, for
// display) live in memory only. The refresh token is kept on the device so an
// installed app stays signed in; it is what a thief would want, which is why
// it never goes anywhere but the identity service.
import { useSyncExternalStore } from 'react'
import { locale, t } from '../i18n.ts'
import { isNative, nativeStore, pushReset, pushSignedOut } from '../native.ts'
import { clearDrafts, loadDevice, setDevice } from '../app/device.ts'
import { AuthError, cognito, type AuthProvider, type Step, type TokenSet } from './cognito.ts'

export { AuthError, type AuthProvider } from './cognito.ts'

const provider: AuthProvider = cognito
const REFRESH_KEY = 'cappy.refresh.v1'

// --- session state ----------------------------------------------------------------

/** `staff` only shapes the UI (the admin menu); every staff call is checked by the server. */
export type Session = { sub: string; email: string; staff: boolean }

type Tokens = { access: string; id: string; expiresAt: number }
let tokens: Tokens | null = null
let session: Session | null = null
/** False until a stored session has been restored or found absent. */
let ready = false
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((fn) => fn())

// On the web the refresh token is in localStorage (under the CSP). In a store
// shell it is in the platform's app storage (Capacitor Preferences), mirrored
// here so reads stay synchronous; the mirror is filled before the first restore.
let mirror: string | null = null

function readRefresh(): string | null {
  if (isNative) return mirror
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

function writeRefresh(value: string | null): void {
  if (isNative) {
    mirror = value
    void (value ? nativeStore.set(REFRESH_KEY, value) : nativeStore.remove(REFRESH_KEY))
    return
  }
  try {
    if (value) localStorage.setItem(REFRESH_KEY, value)
    else localStorage.removeItem(REFRESH_KEY)
  } catch {
    // Storage blocked: signed in for this page load only.
  }
}

function adopt(r: TokenSet): void {
  tokens = { access: r.access, id: r.id, expiresAt: Date.now() + r.expiresIn * 1000 }
  if (r.refresh) writeRefresh(r.refresh)
  session = provider.identity(r)
  writeKnown(session)
  announce(session.sub)
  // A returning device goes straight to sign-in, never the welcome again.
  setDevice({ signedInBefore: true, welcomeSeen: true })
  emit()
}

function forget(): void {
  pushReset()
  tokens = null
  session = null
  writeRefresh(null)
  writeKnown(null)
  announce(null)
  emit()
}

/** The server ended this session (sign out everywhere, a deleted account;
 *  P-24): signed out here and in every tab. Drafts stay, as after an expiry. */
export function endSession(): void {
  if (session || readRefresh()) forget()
}

// Who was signed in, kept beside the refresh token (not a secret: the id, email
// and the staff flag), so a phone opened offline shows the app, not the
// sign-in screen (FL-14). Tokens come back with the network.
const KNOWN_KEY = 'cappy.session.v1'
let knownMirror: string | null = null
function writeKnown(s: Session | null): void {
  const value = s ? JSON.stringify(s) : null
  if (isNative) {
    knownMirror = value
    void (value ? nativeStore.set(KNOWN_KEY, value) : nativeStore.remove(KNOWN_KEY))
    return
  }
  try {
    if (value) localStorage.setItem(KNOWN_KEY, value)
    else localStorage.removeItem(KNOWN_KEY)
  } catch {
    // Storage blocked: offline starts show sign-in.
  }
}
function readKnown(): Session | null {
  try {
    const raw = isNative ? knownMirror : localStorage.getItem(KNOWN_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}
/** The last refresh failed for want of a network, not because it was refused. */
let offlineAtRefresh = false

let refreshing: Promise<boolean> | null = null

/** A new access token from the stored refresh token. False when there is no
 *  usable refresh token (signed out, or it was revoked or expired). */
export function refresh(): Promise<boolean> {
  refreshing ??= (async () => {
    const stored = readRefresh()
    if (!stored) return false
    try {
      adopt(await provider.refresh(stored))
      offlineAtRefresh = false
      return true
    } catch (err) {
      // Offline is not signed out: keep the refresh token for next time.
      offlineAtRefresh = err instanceof AuthError && err.code === 'offline'
      if (!offlineAtRefresh) forget()
      return false
    }
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

/** The access token to send, refreshed a minute before it would expire. */
export async function accessToken(): Promise<string | null> {
  if (tokens && tokens.expiresAt - Date.now() > 60_000) return tokens.access
  if (!readRefresh()) return tokens?.access ?? null
  await refresh()
  return tokens?.access ?? null
}

// Restore whatever this device had, once, at start.
void (async () => {
  await loadDevice()
  if (isNative) {
    mirror = await nativeStore.get(REFRESH_KEY)
    knownMirror = await nativeStore.get(KNOWN_KEY)
  }
  if (readRefresh() && !(await refresh()) && offlineAtRefresh) {
    // Opened offline: the app with its offline bar, signed in as before;
    // tokens when the network is back.
    session = readKnown()
  }
})().finally(() => {
  ready = true
  emit()
})

// Another tab signed out, or in as someone else (V3-7). Tabs follow the
// account's id under its own key, never the refresh token itself: with token
// rotation every refresh rewrites that, and tabs would refresh each other forever.
const WHO_KEY = 'cappy.who.v1'
function announce(sub: string | null): void {
  if (isNative) return
  try {
    if (localStorage.getItem(WHO_KEY) === sub) return
    if (sub) localStorage.setItem(WHO_KEY, sub)
    else localStorage.removeItem(WHO_KEY)
  } catch {
    // Storage blocked: this tab is on its own.
  }
}
if (typeof window !== 'undefined') {
  addEventListener('online', () => {
    if (session && !tokens) void refresh()
  })
}
if (!isNative) {
  addEventListener('storage', (e) => {
    if (e.key !== WHO_KEY || e.newValue === (session?.sub ?? null)) return
    if (!e.newValue) {
      tokens = null
      session = null
      emit()
    } else if (session) {
      // A different account's data is on screen and in the cache: start clean.
      location.reload()
    } else {
      void refresh()
    }
  })
}

const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Who is signed in, or null. */
export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, () => session)
}

/** True once a stored session has been restored (or found absent). */
export function useAuthReady(): boolean {
  return useSyncExternalStore(subscribe, () => ready)
}

// --- the flows ---------------------------------------------------------------------

/** A sign-in waiting for the authenticator app's code (P-4). */
let pending: { email: string; mfa: string } | null = null

/** Resolves once signed in. Throws `AuthError` with code `SOFTWARE_TOKEN_MFA`
 *  when the account has two-step sign-in: answer with `answerMfa(code)`. */
export async function signIn(email: string, password: string): Promise<void> {
  finish(await provider.signIn(email, password), email)
}

export async function answerMfa(code: string): Promise<void> {
  if (!pending) throw new AuthError(t('Sign in again: the code step timed out.'), 'mfa-expired')
  finish(await provider.answerMfa(pending.email, pending.mfa, code), pending.email)
}

function finish(out: Step, email: string): void {
  if ('mfa' in out) {
    pending = { email, mfa: out.mfa }
    throw new AuthError(t('Enter the code from your authenticator app.'), 'SOFTWARE_TOKEN_MFA')
  }
  pending = null
  adopt(out.tokens)
  // The full locale, so emails and pushes use the region's formats too (en-US, fr-CA).
  void updateLocale(locale())
  // Push is asked for later, when it is worth something (push.ts, U-4).
}

/** Two-step sign-in with an authenticator app (TOTP), step 1: the secret to
 *  add to the app, and the `otpauth://` link that adds it in one tap. */
export async function startTotp(): Promise<{ secret: string; uri: string }> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to set up two-step sign-in.'), 'signed-out')
  const secret = await provider.startTotp(access)
  const label = encodeURIComponent(`Cappy:${session?.email ?? ''}`)
  return { secret, uri: `otpauth://totp/${label}?secret=${secret}&issuer=Cappy` }
}

/** Step 2: the first code from the app proves it works; then it is required at every sign-in. */
export async function confirmTotp(code: string): Promise<void> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to set up two-step sign-in.'), 'signed-out')
  await provider.confirmTotp(access, code)
}

/** The language emails and pushes come in (Cognito's standard `locale`). */
export async function updateLocale(value: string): Promise<void> {
  const access = tokens?.access
  if (!access) return
  try {
    await provider.updateLocale(access, value)
  } catch {
    // Best effort: the next sign-in sets it again.
  }
}

export const signUp = (email: string, password: string) => provider.signUp(email, password, locale())
export const confirmSignUp = (email: string, code: string) => provider.confirmSignUp(email, code)
export const resendCode = (email: string) => provider.resendCode(email)
export const forgotPassword = (email: string) => provider.forgotPassword(email)
export const confirmForgotPassword = (email: string, code: string, password: string) =>
  provider.confirmForgotPassword(email, code, password)

/** Deletes the sign-in itself (App Store: accounts are deletable in the app).
 *  Call after the platform has forgotten the person (DELETE /me). */
export async function deleteAccount(): Promise<void> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to delete your account.'), 'signed-out')
  await provider.deleteUser(access)
  forget()
}

/** Signs this device out: its refresh token is revoked, other devices stay
 *  signed in. `everywhere` ends every session of the account (U-35): the
 *  server forgets all push devices and ends every session. */
export async function signOut(opts: { everywhere?: boolean } = {}): Promise<void> {
  const access = tokens?.access
  const stored = readRefresh()
  if (access && opts.everywhere) {
    // Other devices are only signed out if the server says so; if it cannot,
    // this device stays signed in so the person can try again (V3-23).
    const api = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'
    const res = await fetch(`${api}/me/sign-out-everywhere`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${access}` },
    }).catch(() => null)
    if (res?.status === 429) {
      // A few an hour (P-12): the server says when to try again.
      const body = (await res.json().catch(() => ({}))) as { error?: { message?: string } }
      throw new AuthError(t(body.error?.message ?? 'Too many tries. Wait a few minutes and try again.'), 'rate_limited')
    }
    if (!res?.ok)
      throw new AuthError(
        t('Your other devices could not be signed out. Check your connection and try again.'),
        'everywhere',
      )
  }
  if (access) await pushSignedOut(access)
  clearDrafts()
  forget()
  try {
    if (opts.everywhere && access) await provider.signOutEverywhere(access)
    else if (stored) await provider.revoke(stored)
  } catch {
    // Offline: the tokens are gone from this device, which is what matters here.
  }
}
