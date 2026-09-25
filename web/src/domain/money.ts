import type { Cents } from './types.ts'

const exact = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** One format everywhere ("8,00 €"), so the same price never reads two ways. */
export const formatEur = (c: Cents): string => exact.format(c / 100)

/** Always two decimals, for price breakdowns, where columns must line up. */
export const formatEurExact = (c: Cents): string => exact.format(c / 100)

export const euros = (n: number): Cents => Math.round(n * 100)

/** Basis points of a cent amount, rounded to the nearest cent. */
export const bps = (amount: Cents, points: number): Cents =>
  Math.round((amount * points) / 10_000)
