import type { Business } from '../../domain/types.ts'
import { Field, Input } from './ui.tsx'
import { t } from '../../i18n.ts'

export const emptyBusiness: Business = { legalName: '', address: '', registerNumber: '', vatId: '' }

export type BusinessErrors = Partial<Record<keyof Business, string>>

/** A VAT ID in the shape the server accepts (S-4): two letters and 2–13 more;
 *  a German one is DE and 9 digits. Spaces and dots are allowed while typing. */
function vatProblem(raw: string): string | null {
  const v = raw.replace(/[\s.-]/g, '').toUpperCase()
  if (!v) return null
  if (v.startsWith('DE')) return /^DE\d{9}$/.test(v) ? null : t('A German VAT ID is DE and 9 digits.')
  return /^[A-Z]{2}[0-9A-Z]{2,13}$/.test(v) ? null : t('A VAT ID starts with the country’s two letters, then its number.')
}

/** Every missing or malformed field at once (V4-20), keyed by field. */
export function businessErrors(b: Business): BusinessErrors {
  const e: BusinessErrors = {}
  if (b.legalName.trim().length < 2) e.legalName = t('Enter the legal name of the business.')
  if (b.address.trim().length < 8) e.address = t('Enter the full business address.')
  const vat = vatProblem(b.vatId ?? '')
  if (vat) e.vatId = vat
  return e
}

/** The server's field errors (`business.vatId`…) under the business fields (V4-20). */
export function serverBusinessErrors(fields?: { field: string; message: string }[]): BusinessErrors {
  const e: BusinessErrors = {}
  for (const f of fields ?? []) {
    const [head, key] = f.field.split('.')
    if (head === 'business' && key && ['legalName', 'address', 'registerNumber', 'vatId'].includes(key)) {
      e[key as keyof Business] = t(f.message)
    }
  }
  return e
}

/** What the server needs before a business can go live (S-4); null when complete. */
export function businessProblem(b: Business): string | null {
  const e = Object.values(businessErrors(b))
  return e.length ? e.join(' ') : null
}

/** Blank optional fields are left out, as the API expects. */
export const cleanBusiness = (b: Business): Business => ({
  legalName: b.legalName.trim(),
  address: b.address.trim(),
  ...(b.registerNumber?.trim() ? { registerNumber: b.registerNumber.trim() } : {}),
  ...(b.vatId?.trim() ? { vatId: b.vatId.replace(/[\s.-]/g, '').toUpperCase() } : {}),
})

/**
 * A trader's identity, which consumer law requires us to show renters (in
 * the EU: Art. 6a CRD, in Germany § 5b UWG, § 312l BGB). Shown on their
 * listings and at checkout.
 */
export function BusinessFields({
  value,
  onChange,
  id,
  errors = {},
}: {
  value: Business
  onChange: (b: Business) => void
  id: string
  /** Shown under each field once the form has been submitted. */
  errors?: BusinessErrors
}) {
  const set = (k: keyof Business) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="space-y-4 rounded-[var(--radius-control)] border border-[var(--line)] p-4">
      <p className="t-sm text-[var(--ink-3)]">
        {t('Renters see these details, because the law requires it for businesses: their contract is with you.')}
      </p>
      <Field label={t('Legal name')} htmlFor={`${id}-legal`} error={errors.legalName}>
        <Input id={`${id}-legal`} autoComplete="organization" value={value.legalName} onChange={set('legalName')} invalid={Boolean(errors.legalName)} />
      </Field>
      <Field label={t('Business address')} htmlFor={`${id}-addr`} error={errors.address}>
        <Input id={`${id}-addr`} autoComplete="street-address" value={value.address} onChange={set('address')} invalid={Boolean(errors.address)} />
      </Field>
      <Field label={t('Company register number (optional)')} hint={t('The number in your company or trade register, if you have one.')} htmlFor={`${id}-reg`}>
        <Input id={`${id}-reg`} value={value.registerNumber ?? ''} onChange={set('registerNumber')} />
      </Field>
      <Field label={t('VAT / tax ID (optional)')} hint={t('Your VAT number, or your country’s business tax number.')} htmlFor={`${id}-vat`} error={errors.vatId}>
        <Input id={`${id}-vat`} value={value.vatId ?? ''} onChange={set('vatId')} autoCapitalize="characters" invalid={Boolean(errors.vatId)} />
      </Field>
    </div>
  )
}

/** "Your contract is with …" for a trader's listing and checkout (S-4). */
export function TraderNote({ business }: { business?: Business }) {
  if (!business) return null
  return (
    <div className="t-sm rounded-[var(--radius-control)] bg-[var(--sunken)] p-3 text-[var(--ink-2)]">
      <p className="font-semibold text-[var(--ink)]">
        {t('Your contract is with {name}; Cappy is the platform, not your contract partner.', { name: business.legalName })}
      </p>
      <p className="mt-1">
        {business.address}
        {business.registerNumber && ` · ${business.registerNumber}`}
        {business.vatId && ` · ${t('VAT / tax ID')} ${business.vatId}`}
      </p>
    </div>
  )
}
