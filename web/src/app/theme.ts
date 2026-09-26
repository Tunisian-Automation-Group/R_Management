// Appearance (UX-36): System, Light or Dark, stored per device. The dark
// tokens live under :root[data-theme='dark'] in theme.css; public/theme-init.js
// sets the attribute before the first paint, this keeps it in step.
import { useSyncExternalStore } from 'react'

export type Appearance = 'system' | 'light' | 'dark'
const KEY = 'cappy.theme.v1'
const media = typeof matchMedia === 'undefined' ? null : matchMedia('(prefers-color-scheme: dark)')

function read(): Appearance {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

let current: Appearance = read()
const listeners = new Set<() => void>()

function apply(): void {
  const dark = current === 'dark' || (current === 'system' && !!media?.matches)
  const theme = dark ? 'dark' : 'light'
  document.documentElement.dataset.theme = theme
  // The browser chrome and status bar take the page colour of the theme.
  const page = getComputedStyle(document.documentElement).getPropertyValue('--page').trim()
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', page)
  document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme)
}

export function setAppearance(next: Appearance): void {
  current = next
  try {
    if (next === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, next)
  } catch {
    // Not remembered; still applied for this visit.
  }
  apply()
  listeners.forEach((fn) => fn())
}

export function useAppearance(): Appearance {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => current,
  )
}

if (typeof document !== 'undefined') {
  apply()
  media?.addEventListener('change', () => current === 'system' && apply())
  // Another tab changed it: follow, as the language does.
  addEventListener('storage', (e) => {
    if (e.key !== KEY) return
    current = read()
    apply()
    listeners.forEach((fn) => fn())
  })
}
