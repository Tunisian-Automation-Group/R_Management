import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import * as auth from '../../data/auth.ts'
import { AuthError, useSession } from '../../data/auth.ts'
import { useToast } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Field, Input, Segmented } from '../components/ui.tsx'

/** `label:email:password;…` from VITE_DEMO_ACCOUNTS (written by the local bootstrap). */
const DEMO = ((import.meta.env.VITE_DEMO_ACCOUNTS as string | undefined) ?? '')
  .split(';')
  .map((entry) => entry.split(':'))
  .filter((parts) => parts.length === 3)
  .map(([label, email, password]) => ({ label, email, password }))

/** in: sign in · up: create · confirm: the emailed code · forgot / reset: a new password */
type Mode = 'in' | 'up' | 'confirm' | 'forgot' | 'reset'

const COPY: Record<Mode, { title: string; sub: string; submit: string }> = {
  in: { title: 'Welcome back', sub: 'Sign in to book, to list, and to see what is waiting on you.', submit: 'Sign in' },
  up: { title: 'Join Cappy', sub: 'One account to buy hours and to sell them. It takes a minute.', submit: 'Create account' },
  confirm: { title: 'Check your email', sub: 'We sent you a six-digit code. It proves the address is yours.', submit: 'Confirm' },
  forgot: { title: 'Forgot your password?', sub: 'We will email you a code to set a new one.', submit: 'Send code' },
  reset: { title: 'Set a new password', sub: 'Enter the code from the email and your new password.', submit: 'Save password' },
}

/**
 * Sign in, or create an account. One screen, because the person arriving here
 * was in the middle of something (a request, a heart, a listing) and gets sent
 * straight back to it afterwards.
 */
export function Login() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const session = useSession()
  const toast = useToast()
  const next = params.get('next') || '/'

  const [mode, setMode] = useState<Mode>(params.get('mode') === 'up' ? 'up' : 'in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (session) return <Navigate to={next} replace />

  const go = (m: Mode) => {
    setMode(m)
    setError(null)
    setCode('')
  }

  const run = async () => {
    const who = email.trim().toLowerCase()
    switch (mode) {
      case 'in':
        try {
          await auth.signIn(who, password)
          nav(next, { replace: true })
        } catch (err) {
          if (err instanceof AuthError && err.code === 'UserNotConfirmedException') {
            await auth.resendCode(who)
            go('confirm')
            return
          }
          throw err
        }
        return
      case 'up':
        await auth.signUp(who, password)
        go('confirm')
        return
      case 'confirm':
        await auth.confirmSignUp(who, code.trim())
        await auth.signIn(who, password)
        nav(next, { replace: true })
        return
      case 'forgot':
        await auth.forgotPassword(who)
        go('reset')
        return
      case 'reset':
        await auth.confirmForgotPassword(who, code.trim(), password)
        await auth.signIn(who, password)
        toast('Password changed')
        nav(next, { replace: true })
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if ((mode === 'up' || mode === 'reset') && password.length < 8) return setError('Use at least eight characters.')
    setBusy(true)
    try {
      await run()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const needsPassword = mode === 'in' || mode === 'up' || mode === 'reset'
  const needsCode = mode === 'confirm' || mode === 'reset'
  const copy = COPY[mode]

  return (
    <Screen eyebrow="Your account" title={copy.title} sub={copy.sub} back="/">
      {(mode === 'in' || mode === 'up') && (
        <div className="mb-6">
          <Segmented<Mode>
            label="Sign in or create an account"
            value={mode}
            onChange={go}
            options={[
              { value: 'in', label: 'Sign in' },
              { value: 'up', label: 'Create account' },
            ]}
          />
        </div>
      )}

      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label="Email" htmlFor="f-email">
          <Input
            id="f-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            value={email}
            disabled={mode === 'confirm' || mode === 'reset'}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </Field>

        {needsCode && (
          <Field label="Code" htmlFor="f-code">
            <Input
              id="f-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
            />
          </Field>
        )}

        {needsPassword && (
          <Field
            label={mode === 'reset' ? 'New password' : 'Password'}
            hint={mode === 'in' ? undefined : 'At least ten characters, with a number, a capital and a lowercase letter.'}
            htmlFor="f-password"
          >
            <Input
              id="f-password"
              type="password"
              autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}

        {error && (
          <p role="alert" className="text-[14px] font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}

        <Button
          type="submit"
          block
          size="lg"
          disabled={busy || !email || (needsPassword && !password) || (needsCode && !code)}
        >
          {busy ? 'One moment…' : copy.submit}
        </Button>
      </form>

      {mode === 'in' && DEMO.length > 0 && (
        // Local and staging builds only (VITE_DEMO_ACCOUNTS is never set for
        // production): one tap into a seeded account.
        <div className="mt-6 space-y-2" data-testid="demo-accounts">
          {DEMO.map(({ label, email: demoEmail, password: demoPassword }) => (
            <Button
              key={demoEmail}
              variant="secondary"
              className="w-full"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                setError(null)
                try {
                  await auth.signIn(demoEmail, demoPassword)
                  nav(next, { replace: true })
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Could not sign in')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Continue as {label}
            </Button>
          ))}
        </div>
      )}

      <p className="mt-6 text-center text-[13.5px] text-[var(--ink-3)]">
        {mode === 'in' && (
          <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => go('forgot')}>
            Forgot your password?
          </button>
        )}
        {mode === 'confirm' && (
          <button
            type="button"
            className="font-semibold text-[var(--ink)] underline"
            onClick={() =>
              void auth
                .resendCode(email.trim().toLowerCase())
                .then(() => toast('A new code is on its way'))
                .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not send a code.'))
            }
          >
            Send a new code
          </button>
        )}
        {(mode === 'forgot' || mode === 'reset') && (
          <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => go('in')}>
            Back to sign in
          </button>
        )}
      </p>
    </Screen>
  )
}
