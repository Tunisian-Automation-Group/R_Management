// Static accessibility checks over the JSX (U-30), the ones a regex can make
// honestly: every <img> says what it is (alt, "" for decoration), and nothing
// clickable is smaller than 24 × 24 px (WCAG 2.2, 2.5.8). The full audit is
// axe in the browser: Chrome DevTools → Lighthouse → Accessibility on each
// route, desktop and 390 px, EN and DE (docs/runbook.md). Run: npm run check:a11y
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    return statSync(p).isDirectory() ? files(p) : p.endsWith('.tsx') ? [p] : []
  })

// Tailwind heights under 24 px: h-1…h-5 (4–20 px), h-[<24px], and the rem forms.
const SMALL = /(?:^|\s)(?:h|size)-(?:[1-5]|\[(?:1?\d|2[0-3])px\]|\[(?:0?\.\d+|1(?:\.[0-3]\d*)?)rem\])(?:\s|$)/
const problems: string[] = []
for (const f of files('src')) {
  const src = readFileSync(f, 'utf8')
  const line = (i: number) => src.slice(0, i).split('\n').length
  for (const m of src.matchAll(/<img\b[\s\S]*?\/?>/g)) {
    if (!/\balt=/.test(m[0])) problems.push(`${f}:${line(m.index!)} <img> without alt`)
  }
  for (const m of src.matchAll(/<(button|a|Link)\b[\s\S]*?>/g)) {
    const cls = m[0].match(/className=(?:"([^"]*)"|\{`([^`]*)`\})/)
    const c = cls?.[1] ?? cls?.[2] ?? ''
    if (SMALL.test(c) && !/min-h-(?:6|\[2[4-9]px\]|\[[3-9]\d px\])/.test(c)) {
      problems.push(`${f}:${line(m.index!)} <${m[1]}> smaller than 24 px: ${c.trim().slice(0, 80)}`)
    }
  }
}
for (const p of problems) console.error(p)
if (problems.length) process.exit(1)
console.log('a11y: every image has alt text, every target is at least 24 px')
