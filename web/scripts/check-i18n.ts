// Every German entry keeps its English key's {placeholders}: a dropped or
// misspelt one shows "{name}" to people. Run: npm run check:i18n
import { DE } from '../src/i18n.de.ts'

const holes = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
const bad = Object.entries(DE).filter(([en, de]) => holes(en) !== holes(de) || !de.trim())
for (const [en, de] of bad) console.error(`placeholders differ:\n  en: ${en}\n  de: ${de}`)
if (bad.length) process.exit(1)
console.log(`i18n: ${Object.keys(DE).length} German entries, placeholders match`)
