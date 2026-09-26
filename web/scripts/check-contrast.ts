// Every text colour on the backgrounds it is used on, in both themes, measured
// (WCAG 2.2 AA: 4.5:1 for text, 3:1 for large text and UI parts). The comment
// in theme.css states ratios; this makes them true and keeps them true.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/app/theme.css', import.meta.url).pathname, 'utf8')
const block = (start: string) => {
  const i = css.indexOf(start)
  return css.slice(i, css.indexOf('\n}', i))
}
const vars = (text: string) =>
  Object.fromEntries([...text.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/gi)].map((m) => [m[1], m[2]]))
const light = vars(block(':root {'))
const themes = { light, dark: { ...light, ...vars(block(":root[data-theme='dark'] {")) } }

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

const text = ['ink', 'ink-2', 'ink-3', 'ink-4', 'accent-text', 'danger', 'success-text', 'money', 'warn', 'sky-ink', 'focus']
const pairs: [string, string, number][] = [
  ...text.flatMap((fg) => ['page', 'surface', 'sunken'].map((bg) => [fg, bg, 4.5] as [string, string, number])),
  ['on-accent', 'accent', 4.5],
  ['on-badge', 'badge', 4.5],
  ['on-inverse', 'inverse', 4.5],
  ['on-field', 'field', 4.5],
  ['on-field-dim', 'field', 4.5],
  ['accent-bright', 'field', 3],
  ['accent', 'page', 3],
]

let failed = false
for (const [name, t] of Object.entries(themes)) {
  for (const [fg, bg, min] of pairs) {
    if (!t[fg] || !t[bg]) continue
    const r = ratio(t[fg], t[bg])
    if (r < min) {
      failed = true
      console.error(`${name}: --${fg} on --${bg} is ${r.toFixed(2)}:1, needs ${min}:1`)
    }
  }
}
if (failed) process.exit(1)
console.log(`contrast: ${pairs.length} pairs pass in light and dark`)
