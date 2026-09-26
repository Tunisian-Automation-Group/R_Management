import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { device, setDevice } from '../device.ts'
import { ApiError, saveProfile, useDistricts, useMarket, useMarkets } from '../../data/repo.ts'
import { signOut } from '../../data/auth.ts'
import { messageOf, useCappy } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Button, Check, Field, Input, Segmented } from '../components/ui.tsx'
import { BusinessFields, businessErrors, cleanBusiness, emptyBusiness, serverBusinessErrors, type BusinessErrors } from '../components/BusinessFields.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { CountrySelect } from '../components/CountrySelect.tsx'
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
  const [bizErrors, setBizErrors] = useState<BusinessErrors>({})
  // Where they trade (M-2): live markets only; the device's region when Cappy serves it.
  const { live } = useMarkets()
  const guess = useMarket()
  const [country, setCountry] = useState('')
  const where_country = country || (live.includes(guess.country) ? guess.country : live[0] ?? 'DE')
  const market = useMarket(where_country)
  // U-19: optional; picks the tab to land on. Nothing is locked by it.
  const [intent, setIntent] = useState<'rent' | 'earn' | 'both'>(device().intent ?? 'both')
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Only the districts of that country.
  const inCountry = Object.fromEntries(Object.entries(districts.data ?? {}).filter(([, d]) => d.country === where_country))
  const names = Object.keys(inCountry).sort()
  const where = (names.includes(district) && district) || (names.includes(state.search.district) ? state.search.district : names[0]) || ''

  const [tried, setTried] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    // Every problem at once, each under its own field (V4-20), marked invalid too (V5-11).
    const biz = kind === 'business' ? businessErrors(business) : {}
    setBizErrors(biz)
    const problems = [
      name.trim().length < 2 ? t('Tell people what to call you.') : null,
      Object.keys(biz).length ? t('Complete the business details above.') : null,
      !adult ? t('Cappy is for people aged {age} or over: confirm your age to continue.', { age: market.minimumAge }) : null,
    ].filter(Boolean)
    if (problems.length) return setError(problems.join(' '))
    setBusy(true)
    setError(null)
    try {
      await saveProfile({
        name: name.trim(),
        kind,
        district: where,
        country: where_country,
        adult: true,
        ...(kind === 'business' ? { business: cleanBusiness(business) } : {}),
      })
      setDevice({ intent })
      await qc.invalidateQueries({ queryKey: ['me'] })
      if (intent === 'earn') nav('/earn', { replace: true })
    } catch (err) {
      // Each field the server refused goes under that field (V4-20).
      const onForm = err instanceof ApiError ? serverBusinessErrors(err.fields) : {}
      if (Object.keys(onForm).length) setBizErrors(onForm)
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen eyebrow={t('Almost there')} title={t('Tell people who you are')} sub={t('Shown on your listings, bookings and reviews.')}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label={t('Your name')} htmlFor="o-name" error={tried && name.trim().length < 2 ? t('Tell people what to call you.') : undefined}>
          <Input
            id="o-name"
            autoComplete="name"
            invalid={tried && name.trim().length < 2}
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
        {kind === 'business' && <BusinessFields id="o-biz" value={business} onChange={setBusiness} errors={bizErrors} />}
        <Field label={t('Country')} hint={t('Where you rent and lend. Cappy opens country by country.')} htmlFor="o-country">
          <CountrySelect id="o-country" countries={live} value={where_country} onChange={(e) => setCountry(e.target.value)} />
        </Field>
        <Field label={t('Where are you?')} hint={t('Where your listings live and your searches start.')} htmlFor="o-where">
          <DistrictSelect
            id="o-where"
            districts={inCountry}
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
        <Check
          checked={adult}
          onChange={setAdult}
          label={t('I am {age} or older', { age: market.minimumAge })}
          hint={t('Cappy is for adults: bookings are contracts.')}
        />
        {error && (
          <p role="alert" className="text-body font-semibold text-[var(--danger)]">
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
