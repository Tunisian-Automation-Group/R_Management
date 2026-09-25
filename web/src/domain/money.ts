import type { Cents } from './types.ts'
import { locale } from '../i18n.ts'

// ponytail: EUR until the server sends each price's currency (M-3); every
// caller already passes `currency` from the data where it has one.
export const FALLBACK_CURRENCY = 'EUR'

const formatters = new Map<string, Intl.NumberFormat>()
function formatter(currency: string, loc: string): Intl.NumberFormat {
  const key = `${loc}|${currency}`
  let f = formatters.get(key)
  if (!f) {
    f = new Intl.NumberFormat(loc, { style: 'currency', currency })
    formatters.set(key, f)
  }
  return f
}

/** Minor units per major for a currency: 100 for EUR, USD, CAD, GBP; 1 for JPY. */
export const minorPerMajor = (currency = FALLBACK_CURRENCY): number =>
  10 ** (new Intl.NumberFormat('en', { style: 'currency', currency }).resolvedOptions().maximumFractionDigits ?? 2)

/** A price in the reader's format, in the currency it is charged in, never
 *  converted: "8,00 €", "€8.00", "US$8.00", "CA$8.00", "CHF 8.00". */
export const formatMoney = (minor: Cents, currency?: string, loc: string = locale()): string => {
  const code = (currency || FALLBACK_CURRENCY).toUpperCase()
  return formatter(code, loc).format(minor / minorPerMajor(code))
}

/** The currency's own symbol in the reader's format, for price inputs: "€", "$", "CHF". */
export const currencySymbol = (currency?: string, loc: string = locale()): string =>
  formatter((currency || FALLBACK_CURRENCY).toUpperCase(), loc)
    .formatToParts(0)
    .find((p) => p.type === 'currency')?.value ?? (currency || FALLBACK_CURRENCY).toUpperCase()

export const euros = (n: number): Cents => Math.round(n * 100)

/** Basis points of a cent amount, rounded to the nearest cent. */
export const bps = (amount: Cents, points: number): Cents =>
  Math.round((amount * points) / 10_000)
