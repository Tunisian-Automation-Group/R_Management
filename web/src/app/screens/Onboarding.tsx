import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { device, setDevice } from '../device.ts'
import { saveProfile, useDistricts } from '../../data/repo.ts'
import { signOut } from '../../data/auth.ts'
import { messageOf, useCappy } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Check, Field, Input, Segmented } from '../components/ui.tsx'
import { BusinessFields, businessProblem, cleanBusiness, emptyBusiness } from '../components/BusinessFields.tsx'
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
  const [business, setBusiness] = useState(emptyBusiness)
  const [adult, setAdult] = useState(false)
  // U-19: optional; picks the tab to land on. Nothing is locked by it.
  const [intent, setIntent] = useState<'rent' | 'earn' | 'both'>(device().intent ?? 'both')
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const names = Object.keys(districts.data ?? {}).sort()
  const where = district || (names.includes(state.search.district) ? state.search.district : names[0]) || ''

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (name.trim().length < 2) return setError(t('Tell people what to call you.'))
    const bad = kind === 'business' ? businessProblem(business) : null
    if (bad) return setError(bad)
    if (!adult) return setError(t('Cappy is for people aged 18 or over: confirm your age to continue.'))
    setBusy(true)
    setError(null)
    try {
      await saveProfile({
        name: name.trim(),
        kind,
        district: where,
        adult: true,
        ...(kind === 'business' ? { business: cleanBusiness(business) } : {}),
      })
      setDevice({ intent })
      await qc.invalidateQueries({ queryKey: ['me'] })
      if (intent === 'earn') nav('/earn', { replace: true })
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
        {kind === 'business' && <BusinessFields id="o-biz" value={business} onChange={setBusiness} />}
        <Field label={t('Where are you?')} hint={t('Where your listings live and your searches start.')} htmlFor="o-where">
          <DistrictSelect
            id="o-where"
            districts={districts.data ?? {}}
            value={where}
            onChange={(e) => setDistrict(e.target.value)}
          />
        </Field>
        <Field label={t('What brings you to Cappy?')} hint={t('Only decides where you start. You can do both any time.')}>
          <Segmented<'rent' | 'earn' | 'both'>
            label={t('What brings you to Cappy?')}
            value={intent}
            onChange={setIntent}
            options={[
              { value: 'rent', label: t('Renting') },
              { value: 'earn', label: t('Earning') },
              { value: 'both', label: t('Both') },
            ]}
          />
        </Field>
        <Check checked={adult} onChange={setAdult} label={t('I am 18 or older')} hint={t('Cappy is for adults: bookings are contracts.')} />
        {error && (
          <p role="alert" className="text-[0.875rem] font-semibold text-[var(--danger)]">
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
