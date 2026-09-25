// Signing in, with Amazon Cognito, over its JSON API. No SDK: six calls is all
// the app makes, and each is one POST.
//
// Tokens: the access token (sent to /api) and the id token (who this is, for
// display) live in memory only. The refresh token is kept on the device so an
// installed app stays signed in; it is what a thief would want, which is why
// it never goes anywhere but Cognito.
import { useSyncExternalStore } from 'react'
import { lang, t } from '../i18n.ts'
import { isNative, nativeStore, pushSignedOut } from '../native.ts'
import { clearDrafts, loadDevice, setDevice } from '../app/device.ts'

const REGION = import.meta.env.VITE_COGNITO_REGION as string | undefined
const ENDPOINT = (
  (import.meta.env.VITE_COGNITO_ENDPOINT as string | undefined) ??
  (REGION ? `https://cognito-idp.${REGION}.amazonaws.com/` : '')
).replace(/\/?$/, '/')
const CLIENT_ID = (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined) ?? ''
const REFRESH_KEY = 'cappy.refresh.v1'

export class AuthError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message)
  }
}

/** Plain words for what Cognito says, so a person knows what to do next. */
const FRIENDLY: Record<string, string> = {
  NotAuthorizedException: 'That email and password do not match.',
  // Never say whether an address exists: that tells an attacker which emails
  // have accounts. (The reset flow swallows it and carries on.)
  UserNotFoundException: 'Check the email and the code and try again.',
  UsernameExistsException: 'There is already an account with that email. Sign in instead.',
  CodeMismatchException: 'That code is not right. Check the email and try again.',
  EnableSoftwareTokenMFAException: 'That code is not right. Use the newest code your authenticator app shows.',
  ExpiredCodeException: 'That code has expired. Ask for a new one.',
  InvalidPasswordException: 'Use at least 12 characters. A few words you will remember work well.',
  InvalidParameterException: 'Check the email address and try again.',
  LimitExceededException: 'Too many attempts. Wait a few minutes and try again.',
  TooManyRequestsException: 'Too many attempts. Wait a few minutes and try again.',
}

/** One Cognito call. Calls made with an access token (TOTP setup) carry no client id. */
async function cognito<T>(action: string, body: Record<string, unknown>, withClient = true): Promise<T> {
  if (!ENDPOINT || !CLIENT_ID) throw new AuthError(t('Sign-in is not configured for this build.'), 'config')
  let res: Response
  try {
    res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify(withClient ? { ClientId: CLIENT_ID, ...body } : body),
    })
  } catch {
    throw new AuthError(t('Cannot reach the sign-in service. Check your connection.'), 'offline')
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (!res.ok) {
    const code = String(data.__type ?? 'Error')
      .split('#')
      .pop()!
    throw new AuthError(
      FRIENDLY[code] ? t(FRIENDLY[code]) : String(data.message ?? t('That did not work. Try again.')),
      code,
    )
  }
  return data as T
}

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

function claims(jwt: string): Record<string, unknown> {
  const part = jwt.split('.')[1] ?? ''
  const json = atob(
    part
      .replace(/-/g, '+')
      .replace(/_/g, '/')
      .padEnd(Math.ceil(part.length / 4) * 4, '='),
  )
  return JSON.parse(json) as Record<string, unknown>
}

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

type AuthResult = {
  AccessToken: string
  IdToken: string
  ExpiresIn: number
  RefreshToken?: string
}

function adopt(r: AuthResult): void {
  tokens = {
    access: r.AccessToken,
    id: r.IdToken,
    expiresAt: Date.now() + r.ExpiresIn * 1000,
  }
  if (r.RefreshToken) writeRefresh(r.RefreshToken)
  const c = claims(r.IdToken)
  const groups = claims(r.AccessToken)['cognito:groups']
  session = {
    sub: String(c.sub),
    email: String(c.email ?? ''),
    staff: Array.isArray(groups) && groups.includes('admin'),
  }
  announce(session.sub)
  // A returning device goes straight to sign-in, never the welcome again.
  setDevice({ signedInBefore: true, welcomeSeen: true })
  emit()
}

function forget(): void {
  tokens = null
  session = null
  writeRefresh(null)
  announce(null)
  emit()
}

let refreshing: Promise<boolean> | null = null

/** A new access token from the stored refresh token. False when there is no
 *  usable refresh token (signed out, or it was revoked or expired). */
export function refresh(): Promise<boolean> {
  refreshing ??= (async () => {
    const stored = readRefresh()
    if (!stored) return false
    try {
      const out = await cognito<{ AuthenticationResult: AuthResult }>('InitiateAuth', {
        AuthFlow: 'REFRESH_TOKEN_AUTH',
        AuthParameters: { REFRESH_TOKEN: stored },
      })
      adopt(out.AuthenticationResult)
      return true
    } catch (err) {
      // Offline is not signed out: keep the refresh token for next time.
      if (!(err instanceof AuthError && err.code === 'offline')) forget()
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
  if (isNative) mirror = await nativeStore.get(REFRESH_KEY)
  if (readRefresh()) await refresh()
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

type Challenge = {
  AuthenticationResult?: AuthResult
  ChallengeName?: string
  Session?: string
}

/** A sign-in waiting for the authenticator app's code (P-4). */
let pending: { username: string; session: string } | null = null

/** Resolves once signed in. Throws `AuthError` with code `SOFTWARE_TOKEN_MFA`
 *  when the account has two-step sign-in: answer with `answerMfa(code)`. */
export async function signIn(email: string, password: string): Promise<void> {
  const out = await cognito<Challenge>('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: { USERNAME: email, PASSWORD: password },
  })
  finish(out, email)
}

export async function answerMfa(code: string): Promise<void> {
  if (!pending) throw new AuthError(t('Sign in again: the code step timed out.'), 'mfa-expired')
  const out = await cognito<Challenge>('RespondToAuthChallenge', {
    ChallengeName: 'SOFTWARE_TOKEN_MFA',
    Session: pending.session,
    ChallengeResponses: {
      USERNAME: pending.username,
      SOFTWARE_TOKEN_MFA_CODE: code,
    },
  })
  finish(out, pending.username)
}

function finish(out: Challenge, username: string): void {
  if (out.ChallengeName === 'SOFTWARE_TOKEN_MFA' && out.Session) {
    pending = { username, session: out.Session }
    throw new AuthError(t('Enter the code from your authenticator app.'), 'SOFTWARE_TOKEN_MFA')
  }
  if (!out.AuthenticationResult) {
    throw new AuthError(t('This account needs a step this app does not support yet.'), out.ChallengeName ?? 'challenge')
  }
  pending = null
  adopt(out.AuthenticationResult)
  void updateLocale(lang())
  // Push is asked for later, when it is worth something (push.ts, U-4).
}

/** Two-step sign-in with an authenticator app (TOTP), step 1: the secret to
 *  add to the app, and the `otpauth://` link that adds it in one tap. */
export async function startTotp(): Promise<{ secret: string; uri: string }> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to set up two-step sign-in.'), 'signed-out')
  const { SecretCode } = await cognito<{ SecretCode: string }>('AssociateSoftwareToken', { AccessToken: access }, false)
  const label = encodeURIComponent(`Cappy:${session?.email ?? ''}`)
  return {
    secret: SecretCode,
    uri: `otpauth://totp/${label}?secret=${SecretCode}&issuer=Cappy`,
  }
}

/** Step 2: the first code from the app proves it works; then it is required at every sign-in. */
export async function confirmTotp(code: string): Promise<void> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to set up two-step sign-in.'), 'signed-out')
  const out = await cognito<{ Status: string }>(
    'VerifySoftwareToken',
    { AccessToken: access, UserCode: code, FriendlyDeviceName: 'Cappy' },
    false,
  )
  if (out.Status !== 'SUCCESS')
    throw new AuthError(t('That code is not right. Use the newest code your authenticator app shows.'), 'totp')
  await cognito(
    'SetUserMFAPreference',
    {
      AccessToken: access,
      SoftwareTokenMfaSettings: { Enabled: true, PreferredMfa: true },
    },
    false,
  )
}

/** The language emails and pushes come in: Cognito's standard `locale`. */
export async function updateLocale(value: string): Promise<void> {
  const access = tokens?.access
  if (!access || !ENDPOINT) return
  try {
    await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.UpdateUserAttributes',
      },
      body: JSON.stringify({
        AccessToken: access,
        UserAttributes: [{ Name: 'locale', Value: value }],
      }),
    })
  } catch {
    // Best effort: the next sign-in sets it again.
  }
}

export const signUp = (email: string, password: string) =>
  cognito('SignUp', {
    Username: email,
    Password: password,
    UserAttributes: [
      { Name: 'email', Value: email },
      { Name: 'locale', Value: lang() },
    ],
  })

export const confirmSignUp = (email: string, code: string) =>
  cognito('ConfirmSignUp', { Username: email, ConfirmationCode: code })

export const resendCode = (email: string) => cognito('ResendConfirmationCode', { Username: email })

export const forgotPassword = (email: string) => cognito('ForgotPassword', { Username: email })

export const confirmForgotPassword = (email: string, code: string, password: string) =>
  cognito('ConfirmForgotPassword', {
    Username: email,
    ConfirmationCode: code,
    Password: password,
  })

/** Deletes the sign-in itself (App Store: accounts are deletable in the app).
 *  Call after the platform has forgotten the person (DELETE /me). */
export async function deleteAccount(): Promise<void> {
  const access = await accessToken()
  if (!access) throw new AuthError(t('Sign in again to delete your account.'), 'signed-out')
  let res: Response
  try {
    res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.DeleteUser',
      },
      body: JSON.stringify({ AccessToken: access }),
    })
  } catch {
    throw new AuthError(t('Cannot reach the sign-in service. Check your connection.'), 'offline')
  }
  if (!res.ok) throw new AuthError(t('Your sign-in could not be deleted. Try again.'), 'delete')
  forget()
}

/** Signs this device out: its refresh token is revoked, other devices stay
 *  signed in. `everywhere` ends every session of the account (U-35): the
 *  server forgets all push devices, Cognito revokes every token. */
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
    if (opts.everywhere && access) {
      await fetch(ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-amz-json-1.1',
          'X-Amz-Target': 'AWSCognitoIdentityProviderService.GlobalSignOut',
        },
        body: JSON.stringify({ AccessToken: access }),
      })
    } else if (stored) {
      await fetch(ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-amz-json-1.1',
          'X-Amz-Target': 'AWSCognitoIdentityProviderService.RevokeToken',
        },
        body: JSON.stringify({ Token: stored, ClientId: CLIENT_ID }),
      })
    }
  } catch {
    // Offline: the tokens are gone from this device, which is what matters here.
  }
}
