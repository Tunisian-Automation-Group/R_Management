// The rollout bucket must agree with the server's (docs/TASKS.md, Batch S). Run: npm run check:flags
import assert from 'node:assert/strict'
import { bucket, flagOn } from '../src/domain/flags.ts'

assert.equal(bucket('newcheckout', 'user-1'), 16)
assert.equal(flagOn('x', { flags: { x: true } }, undefined), true)
assert.equal(flagOn('newcheckout', { rollouts: { newcheckout: 17 } }, 'user-1'), true)
assert.equal(flagOn('newcheckout', { rollouts: { newcheckout: 16 } }, 'user-1'), false)
assert.equal(flagOn('newcheckout', { rollouts: { newcheckout: 50 } }, undefined), false)
console.log('flags: rollout bucket matches the server')
