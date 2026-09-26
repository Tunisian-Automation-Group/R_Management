// UX-5: colours, text sizes and radii come from the tokens in theme.css.
// A literal anywhere else fails the build. The few that exist today are
// counted in tokens-allowlist.json; the count may only go down.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const rules: Record<string, RegExp> = {
  'text size': /\btext-\[\d[\d.]*(rem|px|em)\]/g,
  radius: /\brounded(-[a-z]+)?-\[\d[\d.]*(px|rem)\]/g,
  hex: /(?<!&)#[0-9a-fA-F]{3,8}\b(?![-\w])/g,
  rgba: /\brgba?\(\s*\d/g,
  'named colour': /\b(bg|text|border|ring|fill|stroke|from|to|via)-(white|black|gray|neutral|red|green|slate|stone|zinc|blue|amber|orange)\b/g,
  'inline font size': /fontSize:\s*\d/g,
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) return walk(p)
    return /\.(tsx|ts)$/.test(f) && !/i18n\./.test(f) ? [p] : []
  })
}

const counts: Record<string, number> = Object.fromEntries(Object.keys(rules).map((k) => [k, 0]))
const where: string[] = []
for (const f of walk('src')) {
  const s = readFileSync(f, 'utf8')
  for (const [name, re] of Object.entries(rules)) {
    const found = s.match(re)
    if (!found) continue
    counts[name] += found.length
    where.push(`${f}: ${found.length} × ${name}`)
  }
}

const allow: Record<string, number> = JSON.parse(readFileSync('scripts/tokens-allowlist.json', 'utf8'))
const over = Object.keys(rules).filter((k) => counts[k] > (allow[k] ?? 0))
const under = Object.keys(rules).filter((k) => counts[k] < (allow[k] ?? 0))
if (over.length) {
  console.error('tokens: literals outside theme.css (use a token instead):')
  for (const k of over) console.error(`  ${k}: ${counts[k]} found, ${allow[k] ?? 0} allowed`)
  for (const w of where) console.error('   ', w)
  process.exit(1)
}
if (under.length) {
  console.error(`tokens: fewer literals than allowed; lower scripts/tokens-allowlist.json to ${JSON.stringify(counts)}`)
  process.exit(1)
}
console.log(`tokens: no new literals (${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(', ')})`)
