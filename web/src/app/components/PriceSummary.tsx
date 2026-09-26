// One price summary for the listing, the confirm sheet and the booking (UX-23):
// the same lines in the same order everywhere, one name for the fee, money in
// figures. The renter sees what they pay; only the owner sees what they get.
import type { ReactNode } from 'react'
import { Row } from './ui.tsx'
import { formatMoney } from '../../domain/money.ts'
import { t } from '../../i18n.ts'

export type PriceLines = {
  /** "€4.00/h × 4 hours" and its amount. */
  base: { label: string; amount: number }
  extra?: { label: string; amount: number }
  discount?: { label: string; amount: number }
  fee: number
  total: number
  /** What the owner receives; shown only when `perspective` is the owner. */
  ownerNet?: number
}

export function PriceSummary({
  lines,
  currency,
  perspective,
  policy,
  after,
}: {
  lines: PriceLines
  currency?: string
  perspective: 'renter' | 'owner'
  /** The dated cancellation line, under the total. */
  policy?: string
  /** Money moved after booking (refunds), as extra rows. */
  after?: ReactNode
}) {
  const m = (n: number) => formatMoney(n, currency)
  return (
    <div>
      <Row label={lines.base.label} value={m(lines.base.amount)} />
      {lines.extra && lines.extra.amount > 0 && <Row label={lines.extra.label} value={m(lines.extra.amount)} />}
      {lines.discount && lines.discount.amount > 0 && (
        <Row label={lines.discount.label} value={`−${m(lines.discount.amount)}`} tone="accent" />
      )}
      <div className="my-2 border-t border-[var(--line)]" />
      <Row label={perspective === 'owner' ? t('Renter pays') : t('Total')} value={m(lines.total)} strong />
      {perspective === 'renter' ? (
        // The fee sits inside the total, so it is said, not added.
        <p className="t-sm tnum text-[var(--ink-4)]">{t('Includes the service fee of {fee}', { fee: m(lines.fee) })}</p>
      ) : (
        <>
          <Row label={t('Service fee')} value={`−${m(lines.fee)}`} tone="muted" />
          {lines.ownerNet !== undefined && <Row label={t('You receive')} value={m(lines.ownerNet)} strong />}
        </>
      )}
      {after}
      {policy && <p className="t-sm mt-3 border-t border-[var(--line)] pt-3 text-[var(--ink-3)]">{policy}</p>}
    </div>
  )
}
