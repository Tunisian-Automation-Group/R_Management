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
// The French legal pages (Legal.tsx) are prose written in the page, not in the
// catalogue: the same typography rule over their French text (V7-9). French is
// the *Fr components, the `fr: (…)` JSX blocks and the `fr:` strings.
{
  const src = readFileSync(new URL('../src/app/screens/Legal.tsx', import.meta.url).pathname, 'utf8')
  const blocks: string[] = []
  for (const m of src.matchAll(/^function \w+Fr\(\)[\s\S]*?(?=^(?:export )?(?:function|const) |(?![\s\S]))/gm)) blocks.push(m[0])
  for (const m of src.matchAll(/\bfr:\s*\(/g)) {
    let depth = 0
    let i = m.index! + m[0].length - 1
    for (; i < src.length; i++) if (src[i] === '(') depth++; else if (src[i] === ')' && --depth === 0) break
    blocks.push(src.slice(m.index!, i))
  }
  const texts: string[] = []
  for (const m of src.matchAll(/\bfr:\s*\[?\s*((?:'(?:[^'\\]|\\.)*'\s*,?\s*)+)/g))
    for (const q of m[1].matchAll(/'((?:[^'\\]|\\.)*)'/g)) texts.push(q[1].replace(/\\u00a0/g, ' ').replace(/\\u202f/g, ' '))
  for (let b of blocks) {
    // Template literals are prose too (the withdrawal form); their ${…} is not.
    for (const m of b.matchAll(/`([^`]*)`/g)) for (const line of m[1].replace(/\$\{[^}]*\}/g, 'X').split('\n')) texts.push(line)
    // Code in braces is not prose; what is left between tags is. Only braces
    // holding no markup go, so a function body never swallows its JSX.
    while (/\{[^{}<>]*\}/.test(b)) b = b.replace(/\{[^{}<>]*\}/g, 'X')
    for (const m of b.matchAll(/>([^<>]+)</g)) texts.push(m[1].replace(/&nbsp;/g, '\u00a0').replace(/&#8239;/g, '\u202f').replace(/[ \t\r\n]+/g, ' '))
  }
  const bad = texts.filter((s) => /[^\u00a0]:(?=[ \t\r\n]|$)|[^\u202f;?!][;?!]/.test(prose(s)))
  for (const s of bad) console.error(`fr (Legal.tsx): typography (U+00A0 before ":", U+202F before ; ? !):\n  ${s.trim()}`)
  if (bad.length) failed = true
}
if (failed || onlyDe.length || onlyFr.length || untranslated.size) process.exit(1)
console.log(`i18n: ${Object.keys(DE).length} German and ${Object.keys(FR).length} French entries, same keys, placeholders match`)
