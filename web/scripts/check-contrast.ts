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
  Object.fromEntries(
    [...text.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6}|var\(--[\w-]+\)|rgba\([^)]*\))/gi)].map((m) => [m[1], m[2]]),
  )
// An alias (--dock-bg: var(--elevated)) takes the value it points at.
const resolve = (t: Record<string, string>) => {
  for (let i = 0; i < 4; i++)
    for (const [k, v] of Object.entries(t)) {
      const ref = /^var\(--([\w-]+)\)$/.exec(v)
      if (ref && t[ref[1]]) t[k] = t[ref[1]]
    }
  for (const [k, v] of Object.entries(t)) if (!v.startsWith('#') && !v.startsWith('rgba')) delete t[k]
  return t
}
// A translucent colour (a hairline) measured where it lies: over its background.
const over = (fg: string, bg: string) => {
  const m = /^rgba\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\s*\)$/.exec(fg)
  if (!m) return fg
  const a = Number(m[4])
  const base = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16))
  return '#' + [1, 2, 3].map((i, j) => Math.round(Number(m[i]) * a + base[j] * (1 - a)).toString(16).padStart(2, '0')).join('')
}
const rawLight = vars(block(':root {'))
const light = resolve({ ...rawLight })
const themes = { light, dark: resolve({ ...rawLight, ...vars(block(":root[data-theme='dark'] {")) }) }

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

const text = ['ink', 'ink-2', 'ink-3', 'ink-4', 'accent-text', 'danger', 'success-text', 'money', 'warn', 'sky-ink', 'focus']
const levels = ['page', 'surface', 'sunken', 'elevated']
// A fourth field limits a pair to one theme.
const pairs: [string, string, number, string?][] = [
  ...text.flatMap((fg) => levels.map((bg) => [fg, bg, 4.5] as [string, string, number])),
  // Body text at 7:1 on the surfaces it is read on (cappy-ui §3).
  ...['ink', 'ink-2'].flatMap((fg) => ['page', 'surface', 'elevated'].map((bg) => [fg, bg, 7] as [string, string, number])),
  // Secondary text holds 4.5:1 up to the overlay step (UX-47).
  ['ink-3', 'overlay', 4.5],
  ['ink-4', 'overlay', 4.5],
  // The dock (UX-46): labels on the bar, the active icon and label on the pill,
  // the pill against the bar, the badge.
  ['ink-3', 'elevated', 4.5],
  ['accent-text', 'accent-subtle', 4.5],
  ['dock-active-ink', 'dock-active', 4.5],
  ['dock-active', 'dock-bg', 1.5],
  ['on-badge', 'badge', 4.5],
  // Disabled controls stay legible (ink-4 on the disabled fill).
  // Disabled controls are exempt from 1.4.3; they stay legible at 3:1.
  ['ink-4', 'disabled-bg', 3],
  // Each surface step is visibly its own level (UX-47).
  // The fills (sunken, surface) step gently; the raised layers step clearly.
  ['sunken', 'page', 1.03, 'dark'],
  ['surface', 'sunken', 1.03, 'dark'],
  // Light is paper on paper, ruled by hairlines; the ladder is dark's.
  ['elevated', 'surface', 1.15, 'dark'],
  ['overlay', 'elevated', 1.15, 'dark'],
  ['pill', 'overlay', 1.15, 'dark'],
  // Dividers and card edges stay visible; input borders are UI parts.
  ['line', 'surface', 1.5],
  ['line', 'page', 1.5],
  ['line', 'elevated', 1.5],
  ['line-strong', 'surface', 3],
  ['on-gallery', 'gallery-bg', 7],
  // The selected segment reads as selected: its label, and its fill on a card.
  ['on-segment', 'segment-on', 4.5],
  ['segment-on', 'surface', 1.5, 'dark'],
]

let failed = false
for (const [name, t] of Object.entries(themes)) {
  for (const [fg, bg, min, only] of pairs) {
    if (only && only !== name) continue
    if (!t[fg] || !t[bg] || t[bg].startsWith('rgba')) continue
    const r = ratio(over(t[fg], t[bg]), t[bg])
    if (r < min) {
      failed = true
      console.error(`${name}: --${fg} on --${bg} is ${r.toFixed(2)}:1, needs ${min}:1`)
    }
  }
}
// Glass (ADR 0014, visual direction §3.4): a fill is only as good as its
// worst backdrop. Composite each glass fill over pure black and pure white
// (a blur averages any real photo to something between the two) and check
// the text allowed on it: ink and ink-2 on glass, white on media glass.
const lite = vars(block(":root[data-glass='lite'] {"))
let glassChecks = 0
for (const [name, t] of Object.entries(themes)) {
  const fills: [string, string][] = ['glass-tint', 'glass-tint-strong'].map((f) => [f, t[f]])
  if (name === 'light') fills.push(['glass-tint (lite)', lite['glass-tint']])
  for (const [fill, value] of fills)
    for (const backdrop of ['#000000', '#ffffff'])
      for (const fg of ['ink', 'ink-2', 'dock-ink']) check(name, fg, t[fg], fill, value, backdrop, 4.5)
  for (const backdrop of ['#ffffff']) {
    check(name, 'white icon', '#ffffff', 'glass-tint-media', t['glass-tint-media'], backdrop, 3)
    check(name, 'white text', '#ffffff', 'glass-tint-media-text', t['glass-tint-media-text'], backdrop, 4.5)
    check(name, 'white text', '#ffffff', 'glass-solid-media', t['glass-solid-media'], backdrop, 4.5)
  }
}
function check(theme: string, fgName: string, fg: string, fill: string, value: string, backdrop: string, min: number) {
  if (!fg || !value) return
  glassChecks++
  const bg = over(value, backdrop)
  const r = ratio(fg, bg)
  if (r < min) {
    failed = true
    console.error(`${theme}: ${fgName} on --${fill} over ${backdrop} is ${r.toFixed(2)}:1, needs ${min}:1`)
  }
}

if (failed) process.exit(1)
console.log(`contrast: ${pairs.length} pairs pass in light and dark, and ${glassChecks} glass worst cases`)
