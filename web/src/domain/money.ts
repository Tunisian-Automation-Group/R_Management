import type { Cents } from './types.ts'

const whole = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})

const exact = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/**
 * Cents are dropped only when there are none. A €3.50 wash must never round to
 * €4, at consumer prices the cents are most of the decision.
 */
export const formatEur = (c: Cents): string =>
  c % 100 === 0 ? whole.format(c / 100) : exact.format(c / 100)

/** Always two decimals, for price breakdowns, where columns must line up. */
export const formatEurExact = (c: Cents): string => exact.format(c / 100)

export const euros = (n: number): Cents => Math.round(n * 100)

/** Basis points of a cent amount, rounded to the nearest cent. */
export const bps = (amount: Cents, points: number): Cents =>
  Math.round((amount * points) / 10_000)
