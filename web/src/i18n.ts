// Languages. gettext-style: the English text is the key, so components read
// naturally and a missing German string falls back to English, never to a
// raw key. The German catalogue lives in ./i18n.de.ts.
//
// The language is module state, not React state: formatting helpers and the
// data layer use it too. Changing it remounts the app (App keys on it), so
// every string re-renders at once.
import { useSyncExternalStore } from 'react'
import { DE } from './i18n.de.ts'

export type Lang = 'en' | 'de'
const KEY = 'cappy.lang.v1'

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'en' || saved === 'de') return saved
  } catch {
    // Storage blocked: fall through to the browser's language.
  }
  return (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en'
}

let current: Lang = initial()
const listeners = new Set<() => void>()
if (typeof document !== 'undefined') document.documentElement.lang = current

export const lang = (): Lang => current
/** The BCP 47 locale for Intl: dates, numbers and money. */
export const locale = (): string => (current === 'de' ? 'de-DE' : 'en-GB')

export function setLang(next: Lang): void {
  if (next === current) return
  current = next
  try {
    localStorage.setItem(KEY, next)
  } catch {
    // Not remembered; still switched for this visit.
  }
  document.documentElement.lang = next
  listeners.forEach((fn) => fn())
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

/** Translate `en` into the current language, filling `{name}` placeholders. */
export function t(en: string, params?: Record<string, string | number>): string {
  const text = current === 'de' ? (DE[en] ?? en) : en
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (m: string, k: string) => (k in params ? String(params[k]) : m))
}

/** One or many: `plural(n, '{n} day', '{n} days')`, both translated. */
export const plural = (n: number, one: string, many: string): string => t(n === 1 ? one : many, { n })
