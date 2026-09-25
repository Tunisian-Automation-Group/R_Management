import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { saveProfile, useDistricts } from '../../data/repo.ts'
import { signOut } from '../../data/auth.ts'
import { messageOf, useCappy } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Field, Input, Segmented, Select } from '../components/ui.tsx'

/**
 * The one step after signing up: what to call you, and where you are. Your
 * listings live there and your searches start there.
 */
export function Onboarding() {
  const qc = useQueryClient()
  const { state } = useCappy()
  const districts = useDistricts()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'person' | 'business'>('person')
  const [district, setDistrict] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const names = Object.keys(districts.data ?? {}).sort()
  const where = district || (names.includes(state.search.district) ? state.search.district : names[0]) || ''

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (name.trim().length < 2) return setError('Tell people what to call you.')
    setBusy(true)
    setError(null)
    try {
      await saveProfile({ name: name.trim(), kind, district: where })
      await qc.invalidateQueries({ queryKey: ['me'] })
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen eyebrow="Almost there" title="Tell people who you are" sub="Shown on your listings, bookings and reviews.">
      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label="Your name" htmlFor="o-name">
          <Input
            id="o-name"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mara Lindqvist"
          />
        </Field>
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
        <Field label="Where are you?" hint="Where your listings live and your searches start." htmlFor="o-where">
          <Select id="o-where" value={where} onChange={(e) => setDistrict(e.target.value)}>
            {names.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </Field>
        {error && (
          <p role="alert" className="text-[14px] font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}
        <Button type="submit" block size="lg" disabled={busy || !where}>
          {busy ? 'One moment…' : 'Continue'}
        </Button>
        <Button type="button" block variant="quiet" onClick={() => void signOut()}>
          Sign out
        </Button>
      </form>
    </Screen>
  )
}
