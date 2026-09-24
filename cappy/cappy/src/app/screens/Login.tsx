import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useCappy } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Field, Input, Segmented, Select } from '../components/ui.tsx'

type Mode = 'in' | 'up'

/**
 * Sign in, or create an account. One screen, because the person arriving here
 * was in the middle of something (a request, a heart, a listing) and gets sent
 * straight back to it afterwards.
 */
export function Login() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const { state, auth } = useCappy()
  const next = params.get('next') || '/'

  const [mode, setMode] = useState<Mode>(params.get('mode') === 'up' ? 'up' : 'in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'person' | 'business'>('person')
  const [district, setDistrict] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (state.session) return <Navigate to={next} replace />

  const districts = Object.keys(state.world.districts)
  const where = district || state.search.district || districts[0] || ''

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (mode === 'up' && name.trim().length < 2) return setError('Tell people what to call you.')
    if (password.length < 8) return setError('Use at least eight characters.')
    setBusy(true)
    try {
      if (mode === 'in') await auth.signIn(email.trim(), password)
      else await auth.register({ email: email.trim(), password, name: name.trim(), kind, district: where })
      nav(next, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen
      eyebrow="Your account"
      title={mode === 'in' ? 'Welcome back' : 'Join Cappy'}
      sub={
        mode === 'in'
          ? 'Sign in to book, to list, and to see what is waiting on you.'
          : 'One account to buy hours and to sell them. It takes a minute.'
      }
      back="/"
    >
      <div className="mb-6">
        <Segmented<Mode>
          label="Sign in or create an account"
          value={mode}
          onChange={(m) => {
            setMode(m)
            setError(null)
          }}
          options={[
            { value: 'in', label: 'Sign in' },
            { value: 'up', label: 'Create account' },
          ]}
        />
      </div>

      <form onSubmit={submit} className="space-y-5" noValidate>
        {mode === 'up' && (
          <Field label="Your name" hint="Shown on your listings and reviews." htmlFor="f-name">
            <Input
              id="f-name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Mara Lindqvist"
            />
          </Field>
        )}

        <Field label="Email" htmlFor="f-email">
          <Input
            id="f-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </Field>

        <Field
          label="Password"
          hint={mode === 'up' ? 'At least eight characters.' : undefined}
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

        {mode === 'up' && (
          <>
            <Field label="You are">
              <Segmented<'person' | 'business'>
                label="Person or business"
                value={kind}
                onChange={setKind}
                options={[
                  { value: 'person', label: 'A person' },
                  { value: 'business', label: 'A business' },
                ]}
              />
            </Field>
            <Field label="Where are you?" hint="Where your listings live and your searches start." htmlFor="f-where">
              <Select id="f-where" value={where} onChange={(e) => setDistrict(e.target.value)}>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            </Field>
          </>
        )}

        {error && (
          <p role="alert" className="text-[14px] font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}

        <Button type="submit" block size="lg" disabled={busy || !email || !password}>
          {busy ? 'One moment…' : mode === 'in' ? 'Sign in' : 'Create account'}
        </Button>
      </form>

      <p className="mt-6 text-center text-[13.5px] text-[var(--ink-3)]">
        {mode === 'in' ? (
          <>
            New here?{' '}
            <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => setMode('up')}>
              Create an account
            </button>
          </>
        ) : (
          <>
            Already have one?{' '}
            <button type="button" className="font-semibold text-[var(--ink)] underline" onClick={() => setMode('in')}>
              Sign in
            </button>
          </>
        )}
      </p>
    </Screen>
  )
}
