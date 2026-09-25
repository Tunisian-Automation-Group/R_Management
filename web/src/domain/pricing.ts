import type { Cents, Listing, Quote, Requirement } from './types.ts'
import { isBatch, isWindow } from './types.ts'
import { bps } from './money.ts'

/** 15% take rate. The fee sits inside the total the buyer pays, it is not added on
 *  top at the last step, because that is the thing everyone hates about marketplaces. */
export const PLATFORM_FEE_BPS = 1500

/**
 * How many hours of the asset this request consumes.
 * `window`, the buyer names the duration.
 * `batch` , setup plus run time, derived from quantity and throughput.
 * Null when the request and listing are different shapes; feasibility rejects those.
 */
export function hoursFor(req: Requirement, listing: Listing): number | null {
  if (req.mode === 'window' && isWindow(listing)) return req.hours
  if (req.mode === 'batch' && isBatch(listing)) {
    return listing.setupHours + req.quantity / listing.unitsPerHour
  }
  return null
}

export function quoteFor(req: Requirement, listing: Listing): Quote | null {
  const hours = hoursFor(req, listing)
  if (hours === null) return null

  const base: Cents = Math.round(hours * listing.ratePerHour)
  const extra: Cents = isWindow(listing) ? listing.extraFee : listing.setupFee
  const extraLabel = isWindow(listing) ? listing.extraLabel : 'Setup and programming'
  const total: Cents = base + extra
  const platformFee = bps(total, PLATFORM_FEE_BPS)

  return {
    hours,
    base,
    extra,
    extraLabel,
    total,
    platformFee,
    ownerNet: total - platformFee,
  }
}
