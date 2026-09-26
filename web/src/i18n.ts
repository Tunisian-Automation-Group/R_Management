// Languages. gettext-style: the English text is the key, so components read
// naturally and a missing translation falls back to English, never to a raw
// key. Catalogues: ./i18n.de.ts (German), ./i18n.fr.ts (French, France and Québec).
//
// The language is module state, not React state: formatting helpers and the
// data layer use it too. Changing it remounts the app (App keys on it), so
// every string re-renders at once.
import { useSyncExternalStore } from 'react'

export type Lang = 'en' | 'de' | 'fr'
/** The language switch's choices, each in its own language. */
export const LANGS: { value: Lang; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'de', label: 'Deutsch' },
  { value: 'fr', label: 'Français' },
]
const KEY = 'cappy.lang.v1'
const isLang = (v: unknown): v is Lang => v === 'en' || v === 'de' || v === 'fr'

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY)
    if (isLang(saved)) return saved
  } catch {
    // Storage blocked: fall through to the browser's language.
  }
  const device = (navigator.language || '').toLowerCase().slice(0, 2)
  return isLang(device) ? device : 'en'
}

let current: Lang = initial()
// A catalogue is fetched only by those who read that language (S-15).
const LOADERS: Record<Exclude<Lang, 'en'>, () => Promise<Record<string, string>>> = {
  de: () => import('./i18n.de.ts').then((m) => m.DE),
  fr: () => import('./i18n.fr.ts').then((m) => m.FR),
}
const catalogues: Partial<Record<Lang, Record<string, string>>> = { en: {} }
async function load(l: Lang): Promise<void> {
  if (l !== 'en' && !catalogues[l]) catalogues[l] = await LOADERS[l]()
}
/** Resolves when the current language's strings are here: render after it. */
export const i18nReady: Promise<void> = load(current)
const listeners = new Set<() => void>()
if (typeof document !== 'undefined') document.documentElement.lang = current

export const lang = (): Lang => current

/** The BCP 47 locale for Intl: dates, numbers, money, units. The app's
 *  language with the device's region, so formats follow the market, not
 *  Germany (GOAL 16): en-US, en-CA, fr-CA, fr-BE, de-AT, de-CH… */
export const locale = (): string => {
  const device = typeof navigator === 'undefined' ? '' : navigator.language || ''
  const region = (device.split('-')[1] ?? '').toUpperCase()
  const own = device.toLowerCase().startsWith(current + '-') ? device : ''
  if (current === 'fr') return region === 'CA' ? 'fr-CA' : own || 'fr-FR'
  // Without an English region of its own, Europe's English: km, 24 h, € (en-IE), never miles.
  if (current === 'en') return region === 'US' || region === 'CA' ? `en-${region}` : own || 'en-IE'
  return own || 'de-DE'
}

export async function setLang(next: Lang, remember = true): Promise<void> {
  if (next === current) return
  await load(next)
  current = next
  if (remember) {
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // Not remembered; still switched for this visit.
    }
  }
  document.documentElement.lang = next
  listeners.forEach((fn) => fn())
}

// Every open tab speaks the language last chosen in any of them (V7-30), so
// an old tab can never send its stale locale to the server again. The storage
// event fires only in the other tabs; they adopt without writing back.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY && isLang(e.newValue)) void setLang(e.newValue, false)
  })
}

export function useLang(): Lang {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => current,
  )
}

/** Pseudo-localisation (U-28), dev builds only: `?pseudo=1` stretches every
 *  string by ~40 % with accents, as German and French run long, so layouts
 *  that break show it without a translator. Kept for the tab; `?pseudo=0` ends it. */
const PSEUDO = (() => {
  if (!import.meta.env.DEV || typeof location === 'undefined') return false
  try {
    const q = new URLSearchParams(location.search).get('pseudo')
    if (q !== null) sessionStorage.setItem('cappy.pseudo', q === '1' ? '1' : '')
    return sessionStorage.getItem('cappy.pseudo') === '1'
  } catch {
    return false
  }
})()
const ACCENT: Record<string, string> = { a: 'á', e: 'ë', i: 'ï', o: 'ö', u: 'ü', A: 'Å', E: 'É', O: 'Ø', c: 'ç', n: 'ñ' }
export const pseudo = (s: string): string => {
  const body = s.replace(/\{\w+\}|[aeiouAEOcn]/g, (m) => (m.length > 1 ? m : ACCENT[m]))
  return `⟦${body}${'·'.repeat(Math.ceil(s.length * 0.4))}⟧`
}

/** Translate `en` into the current language, filling `{name}` placeholders. */
export function t(en: string, params?: Record<string, string | number>): string {
  const found = catalogues[current]?.[en] ?? en
  const text = PSEUDO ? pseudo(found) : found
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (m: string, k: string) => (k in params ? String(params[k]) : m))
}

/** One or many: `plural(n, '{n} day', '{n} days')`, both translated. The
 *  language's own rule decides: French says "0 jour", English "0 days". */
export const plural = (n: number, one: string, many: string): string =>
  t(new Intl.PluralRules(locale()).select(n) === 'one' ? one : many, { n })
