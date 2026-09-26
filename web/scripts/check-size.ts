// The first paint's JavaScript stays small (S-15): the entry chunk that
// index.html loads, gzipped, under the budget. Run after a build: npm run check:size
import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const BUDGET_KB = 170
const html = readFileSync('dist/index.html', 'utf8')
const entry = html.match(/<script[^>]+type="module"[^>]+src="\/?([^"]+\.js)"/)?.[1]
if (!entry) {
  console.error('size: no entry script in dist/index.html; run npm run build first')
  process.exit(1)
}
const kb = gzipSync(readFileSync(`dist/${entry}`)).length / 1000
console.log(`size: entry ${entry} is ${kb.toFixed(1)} kB gzipped (budget ${BUDGET_KB} kB)`)
if (kb > BUDGET_KB) process.exit(1)
