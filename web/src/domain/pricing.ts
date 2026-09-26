/** The Cappy fee, in basis points of the total: inside it, not added on top.
 *  Shown in copy only; every quote comes from the server. */
export const PLATFORM_FEE_BPS = 1500

/** What a booking really moved (V7-2, V7-3). The whole price is taken when it
 *  is confirmed; a refund gives part of it back; Cappy's fee and the owner's
 *  share are of what stays. A request that ended before the card was charged
 *  moved nothing: the server leaves `refundAmount` out then (FL-8). */
export function moved(b: {
  status: string
  noShow?: 'owner' | 'renter'
  refundAmount?: number
  charged?: number
  refunded?: number
  ownerShare?: number
  match: { quote: { total: number } }
}): { charged: number; refunded: number; fee: number; ownerNet: number } {
  // The server's reckoning is the truth (1cb2d67: payments' own figures on
  // the detail, the same rule on lists).
  if (b.charged !== undefined && b.refunded !== undefined && b.ownerShare !== undefined) {
    return { charged: b.charged, refunded: b.refunded, fee: b.charged - b.refunded - b.ownerShare, ownerNet: b.ownerShare }
  }
  // ponytail: fallback for an answer from before the money fields; delete once no client can meet one.
  const taken =
    ['accepted', 'active', 'completed', 'disputed'].includes(b.status) ||
    b.noShow === 'renter' ||
    (b.status === 'cancelled' && b.refundAmount !== undefined)
  const charged = taken ? b.match.quote.total : 0
  const refunded = Math.min(b.refundAmount ?? 0, charged)
  const fee = Math.round(((charged - refunded) * PLATFORM_FEE_BPS) / 10_000)
  return { charged, refunded, fee, ownerNet: charged - refunded - fee }
}
