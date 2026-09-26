// What a booking moved, as the staff Payment card has it (V7-2, V7-3). Run: npm run check:money
import assert from 'node:assert/strict'
import { moved } from '../src/domain/pricing.ts'

const q = (total: number) => ({ match: { quote: { total } } })
// A renter no-show: €8 taken, nothing back, the owner €6.80.
assert.deepEqual(moved({ status: 'cancelled', noShow: 'renter', ...q(800) }), { charged: 800, refunded: 0, fee: 120, ownerNet: 680 })
// Settled at €7 back on €15: the owner €6.80.
assert.deepEqual(moved({ status: 'completed', refundAmount: 700, ...q(1500) }), { charged: 1500, refunded: 700, fee: 120, ownerNet: 680 })
// A request withdrawn before the owner said yes: only a hold, released.
assert.equal(moved({ status: 'cancelled', ...q(1500) }).charged, 0)
assert.equal(moved({ status: 'declined', ...q(1500) }).charged, 0)
// Cancelled after acceptance with everything back.
assert.deepEqual(moved({ status: 'cancelled', refundAmount: 1500, ...q(1500) }), { charged: 1500, refunded: 1500, fee: 0, ownerNet: 0 })
// A late cancellation that gives nothing back still took the price.
assert.equal(moved({ status: 'cancelled', refundAmount: 0, ...q(1500) }).charged, 1500)
console.log('money: charged, refunded and the owner share follow the booking')
