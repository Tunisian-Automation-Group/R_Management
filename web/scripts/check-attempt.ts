// FL-1: a retry after an unknown outcome reuses the key; a known outcome or a
// changed body gets a new one. Run: npm run check:attempt
import { attemptKeys } from '../src/domain/attempt.ts'

let n = 0
const k = attemptKeys(() => `k${++n}`)
const assert = (ok: boolean, what: string) => {
  if (!ok) {
    console.error(`attempt: ${what}`)
    process.exit(1)
  }
}
const body = { slot: 'a' }
const first = k.keyFor(body)
k.settle({ status: 503 })
assert(k.keyFor({ slot: 'a' }) === first, 'a 503 keeps the key')
k.settle({ status: 0 })
assert(k.keyFor(body) === first, 'a lost connection keeps the key')
assert(k.keyFor({ slot: 'b' }) !== first, 'another slot is another key')
const b = k.keyFor({ slot: 'b' })
k.settle({ status: 409 })
assert(k.keyFor({ slot: 'b' }) !== b, 'a definite 4xx ends the attempt')
const c = k.keyFor({ slot: 'b' })
k.settle()
assert(k.keyFor({ slot: 'b' }) !== c, 'a success ends the attempt')
console.log('attempt: keys follow the attempt')
