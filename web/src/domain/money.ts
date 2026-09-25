import type { Cents } from './types.ts'
import { locale } from '../i18n.ts'

// One formatter per locale: "8,00 €" in German, "€8.00" in English.
const formatters = new Map<string, Intl.NumberFormat>()
const exact = () => {
  const l = locale()
  let f = formatters.get(l)
  if (!f) {
    f = new Intl.NumberFormat(l, { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
    formatters.set(l, f)
  }
  return f
}

/** One format everywhere, so the same price never reads two ways. */
export const formatEur = (c: Cents): string => exact().format(c / 100)

/** Always two decimals, for price breakdowns, where columns must line up. */
export const formatEurExact = (c: Cents): string => exact().format(c / 100)

export const euros = (n: number): Cents => Math.round(n * 100)

/** Basis points of a cent amount, rounded to the nearest cent. */
export const bps = (amount: Cents, points: number): Cents =>
  Math.round((amount * points) / 10_000)
