// Every translation keeps its English key's {placeholders}: a dropped or
// misspelt one shows "{name}" to people. French covers exactly the German
// keys, so neither language quietly falls back to English. Run: npm run check:i18n
import { DE } from '../src/i18n.de.ts'
import { FR } from '../src/i18n.fr.ts'

const holes = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
let failed = false
for (const [name, cat] of [['de', DE], ['fr', FR]] as const) {
  const bad = Object.entries(cat).filter(([en, tr]) => holes(en) !== holes(tr) || !tr.trim())
  for (const [en, tr] of bad) console.error(`${name}: placeholders differ:\n  en: ${en}\n  ${name}: ${tr}`)
  failed ||= bad.length > 0
}
const onlyDe = Object.keys(DE).filter((k) => !(k in FR))
const onlyFr = Object.keys(FR).filter((k) => !(k in DE))
for (const k of onlyDe) console.error(`missing in fr: ${k}`)
for (const k of onlyFr) console.error(`missing in de: ${k}`)
if (failed || onlyDe.length || onlyFr.length) process.exit(1)
console.log(`i18n: ${Object.keys(DE).length} German and ${Object.keys(FR).length} French entries, same keys, placeholders match`)
