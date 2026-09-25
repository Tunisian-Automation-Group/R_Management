// Signing in, with Amazon Cognito, over its JSON API. No SDK: six calls is all
// the app makes, and each is one POST.
//
// Tokens: the access token (sent to /api) and the id token (who this is, for
// display) live in memory only. The refresh token is kept on the device so an
// installed app stays signed in; it is what a thief would want, which is why
// it never goes anywhere but Cognito.
import { useSyncExternalStore } from 'react'

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
  ExpiredCodeException: 'That code has expired. Ask for a new one.',
  InvalidPasswordException: 'Use at least ten characters, with a number, a capital and a lowercase letter.',
  InvalidParameterException: 'Check the email address and try again.',
  LimitExceededException: 'Too many attempts. Wait a few minutes and try again.',
  TooManyRequestsException: 'Too many attempts. Wait a few minutes and try again.',
}

async function cognito<T>(action: string, body: Record<string, unknown>): Promise<T> {
  if (!ENDPOINT || !CLIENT_ID) throw new AuthError('Sign-in is not configured for this build.', 'config')
  let res: Response
  try {
    res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify({ ClientId: CLIENT_ID, ...body }),
    })
  } catch {
    throw new AuthError('Cannot reach the sign-in service. Check your connection.', 'offline')
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (!res.ok) {
    const code = String(data.__type ?? 'Error').split('#').pop()!
    throw new AuthError(FRIENDLY[code] ?? String(data.message ?? 'That did not work. Try again.'), code)
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
  const json = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='))
  return JSON.parse(json) as Record<string, unknown>
}

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

function writeRefresh(value: string | null): void {
  try {
    if (value) localStorage.setItem(REFRESH_KEY, value)
    else localStorage.removeItem(REFRESH_KEY)
  } catch {
    // Storage blocked: signed in for this page load only.
  }
}

type AuthResult = { AccessToken: string; IdToken: string; ExpiresIn: number; RefreshToken?: string }

function adopt(r: AuthResult): void {
  tokens = { access: r.AccessToken, id: r.IdToken, expiresAt: Date.now() + r.ExpiresIn * 1000 }
  if (r.RefreshToken) writeRefresh(r.RefreshToken)
  const c = claims(r.IdToken)
  const groups = claims(r.AccessToken)['cognito:groups']
  session = { sub: String(c.sub), email: String(c.email ?? ''), staff: Array.isArray(groups) && groups.includes('admin') }
  emit()
}

function forget(): void {
  tokens = null
  session = null
  writeRefresh(null)
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
void (readRefresh() ? refresh() : Promise.resolve(false)).finally(() => {
  ready = true
  emit()
})

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

export async function signIn(email: string, password: string): Promise<void> {
  const out = await cognito<{ AuthenticationResult?: AuthResult; ChallengeName?: string }>('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: { USERNAME: email, PASSWORD: password },
  })
  if (!out.AuthenticationResult) {
    throw new AuthError('This account needs a step this app does not support yet.', out.ChallengeName ?? 'challenge')
  }
  adopt(out.AuthenticationResult)
}

export const signUp = (email: string, password: string) =>
  cognito('SignUp', { Username: email, Password: password, UserAttributes: [{ Name: 'email', Value: email }] })

export const confirmSignUp = (email: string, code: string) =>
  cognito('ConfirmSignUp', { Username: email, ConfirmationCode: code })

export const resendCode = (email: string) => cognito('ResendConfirmationCode', { Username: email })

export const forgotPassword = (email: string) => cognito('ForgotPassword', { Username: email })

export const confirmForgotPassword = (email: string, code: string, password: string) =>
  cognito('ConfirmForgotPassword', { Username: email, ConfirmationCode: code, Password: password })

/** Deletes the sign-in itself (App Store: accounts are deletable in the app).
 *  Call after the platform has forgotten the person (DELETE /me). */
export async function deleteAccount(): Promise<void> {
  const access = await accessToken()
  if (!access) throw new AuthError('Sign in again to delete your account.', 'signed-out')
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
    throw new AuthError('Cannot reach the sign-in service. Check your connection.', 'offline')
  }
  if (!res.ok) throw new AuthError('Your sign-in could not be deleted. Try again.', 'delete')
  forget()
}

/** Ends the session everywhere Cognito can, and on this device regardless. */
export async function signOut(): Promise<void> {
  const access = tokens?.access
  forget()
  if (!access) return
  try {
    await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.GlobalSignOut',
      },
      body: JSON.stringify({ AccessToken: access }),
    })
  } catch {
    // Offline: the tokens are gone from this device, which is what matters here.
  }
}
