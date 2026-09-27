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

function apply(tries = 0): void {
  const dark = isDark()
  const theme = dark ? 'dark' : 'light'
  document.documentElement.dataset.theme = theme
  // The browser chrome and status bar take the page colour of the theme.
  // The stylesheet may not be there yet (the dev server injects CSS late):
  // try again on the next frames rather than writing an empty colour (V9-10).
  const page = getComputedStyle(document.documentElement).getPropertyValue('--page').trim()
  if (page) document.querySelector('meta[name="theme-color"]')?.setAttribute('content', page)
  else if (tries < 30) requestAnimationFrame(() => apply(tries + 1))
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
  // One tap flips what is on screen, exactly as the label says; System lives
  // in Appearance (V9-9).
  const next: Appearance = isDark() ? 'light' : 'dark'
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

// Glass effects (VD-5): Full or Reduced, per device. Unset means automatic:
// theme-init.js decides before the first paint, and the first real scroll is
// timed once; if more than a fifth of its frames take over 20 ms, this device
// gets the lite glass from then on.
export type Glass = 'auto' | 'full' | 'lite'
const GLASS = 'cappy.glass.v1'
const glassListeners = new Set<() => void>()

function readGlass(): Glass {
  try {
    const v = localStorage.getItem(GLASS)
    return v === 'full' || v === 'lite' ? v : 'auto'
  } catch {
    return 'auto'
  }
}
let glass: Glass = readGlass()

export function setGlass(next: Glass): void {
  glass = next
  try {
    if (next === 'auto') localStorage.removeItem(GLASS)
    else localStorage.setItem(GLASS, next)
  } catch {
    // Not remembered; still applied for this visit.
  }
  let mode: string = next
  if (next === 'auto') {
    try {
      mode = localStorage.getItem('cappy.glass.auto') === 'lite' ? 'lite' : 'full'
    } catch {
      mode = 'full'
    }
  }
  document.documentElement.dataset.glass = mode
  glassListeners.forEach((fn) => fn())
}

export function useGlass(): Glass {
  return useSyncExternalStore(
    (fn) => {
      glassListeners.add(fn)
      return () => glassListeners.delete(fn)
    },
    () => glass,
  )
}

function probeFirstScroll(): void {
  if (glass !== 'auto' || document.documentElement.dataset.glass === 'lite') return
  const start = () => {
    removeEventListener('scroll', start)
    const frames: number[] = []
    let last = performance.now()
    const tick = (now: number) => {
      frames.push(now - last)
      last = now
      if (frames.length < 60) requestAnimationFrame(tick)
      else if (frames.filter((d) => d > 20).length > frames.length / 5 && document.visibilityState === 'visible') {
        try {
          localStorage.setItem('cappy.glass.auto', 'lite')
        } catch {
          // Only this visit, then.
        }
        document.documentElement.dataset.glass = 'lite'
      }
    }
    requestAnimationFrame(tick)
  }
  addEventListener('scroll', start, { passive: true })
}

if (typeof document !== 'undefined') probeFirstScroll()
