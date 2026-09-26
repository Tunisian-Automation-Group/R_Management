// Appearance (UX-36): Light (the default), Dark or System, stored per device.
// Light is the default for everyone: dark is opt-in, one tap away in the header. The dark
// tokens live under :root[data-theme='dark'] in theme.css; public/theme-init.js
// sets the attribute before the first paint, this keeps it in step.
import { useSyncExternalStore } from 'react'

export type Appearance = 'system' | 'light' | 'dark'
const KEY = 'cappy.theme.v1'
const media = typeof matchMedia === 'undefined' ? null : matchMedia('(prefers-color-scheme: dark)')

function read(): Appearance {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'system' || v === 'dark' ? v : 'light'
  } catch {
    return 'light'
  }
}

let current: Appearance = read()
const listeners = new Set<() => void>()

const isDark = () => current === 'dark' || (current === 'system' && !!media?.matches)

function apply(): void {
  const dark = isDark()
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
    localStorage.setItem(KEY, next)
  } catch {
    // Not remembered; still applied for this visit.
  }
  apply()
  listeners.forEach((fn) => fn())
}

/** The one-tap switch (UX-48): Light → Dark → System → Light, crossfaded
 *  in 150 ms where the browser can (none under reduced motion). Returns the
 *  new choice so the caller can say it. */
export function toggleTheme(): Appearance {
  const next: Appearance = current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light'
  const quiet = matchMedia('(prefers-reduced-motion: reduce)').matches
  const doc = document as Document & { startViewTransition?: (fn: () => void) => unknown }
  if (doc.startViewTransition && !quiet) {
    document.documentElement.dataset.themeFade = ''
    doc.startViewTransition(() => setAppearance(next))
    setTimeout(() => delete document.documentElement.dataset.themeFade, 400)
  } else setAppearance(next)
  return next
}

/** What is on screen now, for the switch's icon and label. */
export function useDark(): boolean {
  useAppearance()
  return isDark()
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
