import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { saveProfile, useDistricts } from '../../data/repo.ts'
import { signOut } from '../../data/auth.ts'
import { messageOf, useCappy } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Field, Input, Segmented } from '../components/ui.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { t } from '../../i18n.ts'

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
    if (name.trim().length < 2) return setError(t('Tell people what to call you.'))
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
    <Screen eyebrow={t('Almost there')} title={t('Tell people who you are')} sub={t('Shown on your listings, bookings and reviews.')}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label={t('Your name')} htmlFor="o-name">
          <Input
            id="o-name"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mara Lindqvist"
          />
        </Field>
        <Field label={t('You are')}>
          <Segmented<'person' | 'business'>
            label={t('Person or business')}
            value={kind}
            onChange={setKind}
            options={[
              { value: 'person', label: t('A person') },
              { value: 'business', label: t('A business') },
            ]}
          />
        </Field>
        <Field label={t('Where are you?')} hint={t('Where your listings live and your searches start.')} htmlFor="o-where">
          <DistrictSelect
            id="o-where"
            districts={districts.data ?? {}}
            value={where}
            onChange={(e) => setDistrict(e.target.value)}
          />
        </Field>
        {error && (
          <p role="alert" className="text-[14px] font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}
        <p className="t-sm text-[var(--ink-3)]">
          {t('By continuing you accept the')} <a className="underline" href="/legal/terms">{t('Terms')}</a>{' '}
          {t('and have read the')} <a className="underline" href="/legal/privacy">{t('Privacy Policy')}</a>.
        </p>
        <Button type="submit" block size="lg" disabled={busy || !where}>
          {busy ? t('One moment…') : t('Continue')}
        </Button>
        <Button type="button" block variant="quiet" onClick={() => void signOut()}>
          {t('Sign out')}
        </Button>
      </form>
    </Screen>
  )
}
