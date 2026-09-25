import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import * as auth from '../../data/auth.ts'
import { AuthError, useSession } from '../../data/auth.ts'
import { useToast } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Field, Input, Segmented } from '../components/ui.tsx'
import { t } from '../../i18n.ts'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// NIST 800-63B-4: length, not composition (U-15), as the pool requires.
const STRONG = /^.{12,}$/u

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
  reset: { title: 'Set a new password', sub: 'If there is an account for that email, we have sent it a code. Enter it with your new password.', submit: 'Save password' },
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
  const [reveal, setReveal] = useState(false)
  // A new code can be asked for every 30 s (U-16), which is also Cognito's pace.
  const [cooldown, setCooldown] = useState(0)
  useEffect(() => {
    if (cooldown <= 0) return
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(id)
  }, [cooldown])
  useEffect(() => {
    if (mode === 'confirm' || mode === 'reset') setCooldown(30)
  }, [mode])
  // Six digits typed or pasted from the email: confirm at once.
  useEffect(() => {
    if (mode === 'confirm' && /^\d{6}$/.test(code) && !busy) document.getElementById('f-submit')?.click()
  }, [code, mode])

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
        // Never say whether an account exists: an unknown address goes on to
        // the code step like a known one (no code will arrive).
        try {
          await auth.forgotPassword(who)
        } catch (e) {
          if (!(e instanceof AuthError && e.code === 'UserNotFoundException')) throw e
        }
        go('reset')
        return
      case 'reset':
        await auth.confirmForgotPassword(who, code.trim(), password)
        await auth.signIn(who, password)
        toast(t('Password changed'))
        nav(next, { replace: true })
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!EMAIL.test(email.trim())) return setError(t('Enter your email address, like name@example.com.'))
    // The same rule as the user pool (infra/platform/identity.tf), so nobody is
    // turned away by the server for something the form could have said.
    if ((mode === 'up' || mode === 'reset') && !STRONG.test(password)) {
      return setError(t('Use at least 12 characters. A few words you will remember work well.'))
    }
    setBusy(true)
    try {
      await run()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('That did not work. Try again.'))
    } finally {
      setBusy(false)
    }
  }

  const needsPassword = mode === 'in' || mode === 'up' || mode === 'reset'
  const needsCode = mode === 'confirm' || mode === 'reset'
  const copy = { title: t(COPY[mode].title), sub: t(COPY[mode].sub), submit: t(COPY[mode].submit) }

  return (
    <Screen eyebrow={t('Your account')} title={copy.title} sub={copy.sub} back="/welcome">
      {(mode === 'in' || mode === 'up') && (
        <div className="mb-6">
          <Segmented<Mode>
            label={t('Sign in or create an account')}
            value={mode}
            onChange={go}
            options={[
              { value: 'in', label: t('Sign in') },
              { value: 'up', label: t('Create account') },
            ]}
          />
        </div>
      )}

      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label={t('Email')} htmlFor="f-email">
          <Input
            id="f-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            value={email}
            disabled={mode === 'confirm' || mode === 'reset'}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t('you@example.com')}
          />
        </Field>

        {needsCode && (
          <Field label={t('Code')} htmlFor="f-code">
            <Input
              id="f-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              maxLength={6}
              pattern="[0-9]*"
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
            />
          </Field>
        )}

        {needsPassword && (
          <Field
            label={mode === 'reset' ? t('New password') : t('Password')}
            hint={mode === 'in' ? undefined : t('At least 12 characters. Any characters, spaces too; paste is fine.')}
            htmlFor="f-password"
          >
            <div className="relative">
              <Input
                id="f-password"
                type={reveal ? 'text' : 'password'}
                autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pr-20"
              />
              <button
                type="button"
                aria-pressed={reveal}
                aria-controls="f-password"
                onClick={() => setReveal((r) => !r)}
                className="absolute inset-y-0 right-0 min-w-[64px] px-3 text-[13px] font-semibold text-[var(--ink-3)] hover:text-[var(--ink)]"
              >
                {reveal ? t('Hide') : t('Show')}
              </button>
            </div>
          </Field>
        )}

        {error && (
          <p role="alert" className="text-[14px] font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}

        <Button
          id="f-submit"
          type="submit"
          block
          size="lg"
          disabled={busy || !email || (needsPassword && !password) || (needsCode && !code)}
        >
          {busy ? t('One moment…') : copy.submit}
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
                  setError(e instanceof Error ? e.message : t('Could not sign in'))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Continue as {label}', { label: t(label) })}
            </Button>
          ))}
        </div>
      )}

      <p className="mt-6 text-center text-[13.5px] text-[var(--ink-3)]">
        {mode === 'in' && (
          <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => go('forgot')}>
            {t('Forgot your password?')}
          </button>
        )}
        {mode === 'confirm' && (
          <button
            type="button"
            className="font-semibold text-[var(--ink)] underline disabled:text-[var(--ink-4)] disabled:no-underline"
            disabled={cooldown > 0}
            onClick={() =>
              void auth
                .resendCode(email.trim().toLowerCase())
                .then(() => {
                  setCooldown(30)
                  toast(t('A new code is on its way'))
                })
                .catch((err: unknown) => setError(err instanceof Error ? err.message : t('Could not send a code.')))
            }
          >
            {cooldown > 0 ? t('Send a new code in {n} s', { n: cooldown }) : t('Send a new code')}
          </button>
        )}
        {(mode === 'forgot' || mode === 'reset') && (
          <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => go('in')}>
            {t('Back to sign in')}
          </button>
        )}
      </p>

      {(mode === 'in' || mode === 'up') && (
        // U-18: why there is nothing to see before signing in.
        <p className="t-sm mx-auto mt-8 max-w-[44ch] border-t border-[var(--line)] pt-6 text-center text-[var(--ink-3)]">
          {t('Cappy is for members: listings are people’s own things, places and times, so everyone signs in before seeing them.')}{' '}
          <Link to="/help/safety" className="font-semibold text-[var(--ink)] underline">
            {t('How we keep you safe')}
          </Link>
        </p>
      )}
    </Screen>
  )
}
