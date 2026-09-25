import type { Business } from '../../domain/types.ts'
import { Field, Input } from './ui.tsx'
import { t } from '../../i18n.ts'

export const emptyBusiness: Business = { legalName: '', address: '', registerNumber: '', vatId: '' }

/** What the server needs before a business can go live (S-4); null when complete. */
export function businessProblem(b: Business): string | null {
  if (b.legalName.trim().length < 2) return t('Enter the legal name of the business.')
  if (b.address.trim().length < 8) return t('Enter the full business address.')
  return null
}

/** Blank optional fields are left out, as the API expects. */
export const cleanBusiness = (b: Business): Business => ({
  legalName: b.legalName.trim(),
  address: b.address.trim(),
  ...(b.registerNumber?.trim() ? { registerNumber: b.registerNumber.trim() } : {}),
  ...(b.vatId?.trim() ? { vatId: b.vatId.trim() } : {}),
})

/**
 * A trader's identity, which consumer law requires us to show renters (in
 * the EU: Art. 6a CRD, in Germany § 5b UWG, § 312l BGB). Shown on their
 * listings and at checkout.
 */
export function BusinessFields({ value, onChange, id }: { value: Business; onChange: (b: Business) => void; id: string }) {
  const set = (k: keyof Business) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="space-y-4 rounded-[var(--radius-control)] border border-[var(--line)] p-4">
      <p className="t-sm text-[var(--ink-3)]">
        {t('Renters see these details, because the law requires it for businesses: their contract is with you.')}
      </p>
      <Field label={t('Legal name')} htmlFor={`${id}-legal`}>
        <Input id={`${id}-legal`} autoComplete="organization" value={value.legalName} onChange={set('legalName')} />
      </Field>
      <Field label={t('Business address')} htmlFor={`${id}-addr`}>
        <Input id={`${id}-addr`} autoComplete="street-address" value={value.address} onChange={set('address')} />
      </Field>
      <Field label={t('Company register number (optional)')} hint={t('The number in your company or trade register, if you have one.')} htmlFor={`${id}-reg`}>
        <Input id={`${id}-reg`} value={value.registerNumber ?? ''} onChange={set('registerNumber')} />
      </Field>
      <Field label={t('VAT / tax ID (optional)')} hint={t('Your VAT number, or your country’s business tax number.')} htmlFor={`${id}-vat`}>
        <Input id={`${id}-vat`} value={value.vatId ?? ''} onChange={set('vatId')} autoCapitalize="characters" />
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
