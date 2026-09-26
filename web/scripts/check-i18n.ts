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
// French typography, the rule the server's emails follow too: a no-break
// space (U+00A0) before ":", a narrow no-break space (U+202F) before ; ? !
// ("?!" may follow its own mark). URLs, {placeholders} and clock times are
// not prose and are left out.
const prose = (s: string) =>
  s.replace(/(?:https?:\/\/|mailto:)\S+/g, 'X').replace(/\{\w+\}/g, 'X').replace(/\b\d{1,2}:\d{2}\b/g, 'X')
const typo = Object.entries(FR).filter(([, tr]) => /[^ ]:|[^ ;?!][;?!]/.test(prose(tr)))
for (const [en, tr] of typo) console.error(`fr: typography (U+00A0 before ":", U+202F before ; ? !):\n  en: ${en}\n  fr: ${tr}`)
failed ||= typo.length > 0
const onlyDe = Object.keys(DE).filter((k) => !(k in FR))
const onlyFr = Object.keys(FR).filter((k) => !(k in DE))
for (const k of onlyDe) console.error(`missing in fr: ${k}`)
for (const k of onlyFr) console.error(`missing in de: ${k}`)
// Every literal t('…') and plural(n, '…', '…') in the app has its German (and
// so French) entry: a new string cannot ship in English only. Keys built at
// runtime (t(LABELS[x])) are not seen here; keep their tables next to a literal.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
const sources: string[] = []
const walk = (dir: string) => {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) walk(p)
    else if (/\.tsx?$/.test(f) && !/^i18n\./.test(f)) sources.push(p)
  }
}
walk(new URL('../src', import.meta.url).pathname)
const unq = (s: string) => s.replace(/\\'/g, "'")
const untranslated = new Set<string>()
for (const file of sources) {
  const src = readFileSync(file, 'utf8')
  for (const m of src.matchAll(/\bt\(\s*'((?:[^'\\]|\\.)*)'/g)) if (!(unq(m[1]) in DE)) untranslated.add(`${file}: ${unq(m[1])}`)
  for (const m of src.matchAll(/\bplural\([^,]+,\s*'((?:[^'\\]|\\.)*)',\s*'((?:[^'\\]|\\.)*)'/g))
    for (const k of [m[1], m[2]].map(unq)) if (!(k in DE)) untranslated.add(`${file}: ${k}`)
}
for (const u of untranslated) console.error(`no translation: ${u}`)
if (failed || onlyDe.length || onlyFr.length || untranslated.size) process.exit(1)
console.log(`i18n: ${Object.keys(DE).length} German and ${Object.keys(FR).length} French entries, same keys, placeholders match`)
