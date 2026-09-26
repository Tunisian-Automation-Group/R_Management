// Amazon Cognito as the app's identity provider (F-2), over its JSON API. No
// SDK: each call is one POST. Everything Cognito-shaped lives here; auth.ts
// keeps the session, storage and tabs, and talks to an `AuthProvider`. Another
// identity service is another object with the same shape.
import { t } from '../i18n.ts'

export class AuthError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message)
  }
}

/** What a sign-in yields: tokens, or a second step (the authenticator app's code). */
export type TokenSet = { access: string; id: string; expiresIn: number; refresh?: string }
export type Step = { tokens: TokenSet } | { mfa: string }
/** Who the tokens say this is. `staff` only shapes the UI; the server checks it. */
export type Identity = { sub: string; email: string; staff: boolean }

/** Everything the app needs from an identity service. Errors are `AuthError`s
 *  in plain words, with `code: 'offline'` when it cannot be reached. */
export type AuthProvider = {
  signIn(email: string, password: string): Promise<Step>
  answerMfa(email: string, mfa: string, code: string): Promise<Step>
  refresh(refreshToken: string): Promise<TokenSet>
  identity(tokens: TokenSet): Identity
  signUp(email: string, password: string, locale: string): Promise<void>
  confirmSignUp(email: string, code: string): Promise<void>
  resendCode(email: string): Promise<void>
  forgotPassword(email: string): Promise<void>
  confirmForgotPassword(email: string, code: string, password: string): Promise<void>
  /** Two-step sign-in with an authenticator app: the secret to add, then the first code. */
  startTotp(access: string): Promise<string>
  confirmTotp(access: string, code: string): Promise<void>
  updateLocale(access: string, locale: string): Promise<void>
  deleteUser(access: string): Promise<void>
  /** This device's session only. */
  revoke(refreshToken: string): Promise<void>
  /** Every session of the account. */
  signOutEverywhere(access: string): Promise<void>
}

const REGION = import.meta.env.VITE_COGNITO_REGION as string | undefined
const ENDPOINT = (
  (import.meta.env.VITE_COGNITO_ENDPOINT as string | undefined) ??
  (REGION ? `https://cognito-idp.${REGION}.amazonaws.com/` : '')
).replace(/\/?$/, '/')
const CLIENT_ID = (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined) ?? ''

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
async function call<T>(action: string, body: Record<string, unknown>, withClient = true): Promise<T> {
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
    throw new AuthError(FRIENDLY[code] ? t(FRIENDLY[code]) : String(data.message ?? t('That did not work. Try again.')), code)
  }
  return data as T
}

type AuthResult = { AccessToken: string; IdToken: string; ExpiresIn: number; RefreshToken?: string }
type Challenge = { AuthenticationResult?: AuthResult; ChallengeName?: string; Session?: string }

const tokenSet = (r: AuthResult): TokenSet => ({
  access: r.AccessToken,
  id: r.IdToken,
  expiresIn: r.ExpiresIn,
  refresh: r.RefreshToken,
})

function step(out: Challenge): Step {
  if (out.ChallengeName === 'SOFTWARE_TOKEN_MFA' && out.Session) return { mfa: out.Session }
  if (!out.AuthenticationResult) {
    throw new AuthError(t('This account needs a step this app does not support yet.'), out.ChallengeName ?? 'challenge')
  }
  return { tokens: tokenSet(out.AuthenticationResult) }
}

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

export const cognito: AuthProvider = {
  signIn: async (email, password) =>
    step(
      await call<Challenge>('InitiateAuth', {
        AuthFlow: 'USER_PASSWORD_AUTH',
        AuthParameters: { USERNAME: email, PASSWORD: password },
      }),
    ),
  answerMfa: async (email, mfa, code) =>
    step(
      await call<Challenge>('RespondToAuthChallenge', {
        ChallengeName: 'SOFTWARE_TOKEN_MFA',
        Session: mfa,
        ChallengeResponses: { USERNAME: email, SOFTWARE_TOKEN_MFA_CODE: code },
      }),
    ),
  refresh: async (refreshToken) =>
    tokenSet(
      (
        await call<{ AuthenticationResult: AuthResult }>('InitiateAuth', {
          AuthFlow: 'REFRESH_TOKEN_AUTH',
          AuthParameters: { REFRESH_TOKEN: refreshToken },
        })
      ).AuthenticationResult,
    ),
  identity: (tokens) => {
    const c = claims(tokens.id)
    const groups = claims(tokens.access)['cognito:groups']
    return { sub: String(c.sub), email: String(c.email ?? ''), staff: Array.isArray(groups) && groups.includes('admin') }
  },
  signUp: async (email, password, locale) => {
    await call('SignUp', {
      Username: email,
      Password: password,
      UserAttributes: [
        { Name: 'email', Value: email },
        { Name: 'locale', Value: locale },
      ],
    })
  },
  confirmSignUp: async (email, code) => {
    await call('ConfirmSignUp', { Username: email, ConfirmationCode: code })
  },
  resendCode: async (email) => {
    await call('ResendConfirmationCode', { Username: email })
  },
  forgotPassword: async (email) => {
    await call('ForgotPassword', { Username: email })
  },
  confirmForgotPassword: async (email, code, password) => {
    await call('ConfirmForgotPassword', { Username: email, ConfirmationCode: code, Password: password })
  },
  startTotp: async (access) =>
    (await call<{ SecretCode: string }>('AssociateSoftwareToken', { AccessToken: access }, false)).SecretCode,
  confirmTotp: async (access, code) => {
    const out = await call<{ Status: string }>(
      'VerifySoftwareToken',
      { AccessToken: access, UserCode: code, FriendlyDeviceName: 'Cappy' },
      false,
    )
    if (out.Status !== 'SUCCESS')
      throw new AuthError(t('That code is not right. Use the newest code your authenticator app shows.'), 'totp')
    await call(
      'SetUserMFAPreference',
      { AccessToken: access, SoftwareTokenMfaSettings: { Enabled: true, PreferredMfa: true } },
      false,
    )
  },
  updateLocale: async (access, locale) => {
    await call('UpdateUserAttributes', { AccessToken: access, UserAttributes: [{ Name: 'locale', Value: locale }] }, false)
  },
  deleteUser: async (access) => {
    try {
      await call('DeleteUser', { AccessToken: access }, false)
    } catch (err) {
      if (err instanceof AuthError && err.code === 'offline') throw err
      throw new AuthError(t('Your sign-in could not be deleted. Try again.'), 'delete')
    }
  },
  revoke: async (refreshToken) => {
    await call('RevokeToken', { Token: refreshToken })
  },
  signOutEverywhere: async (access) => {
    await call('GlobalSignOut', { AccessToken: access }, false)
  },
}
