// Navigation with continuity. Every route change runs inside a view transition
// when the browser has one, so screens crossfade and a tapped cover morphs into
// the detail's hero instead of cutting. Reduced motion turns all of it off.
import { useCallback, useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'

type Doc = Document & {
  startViewTransition?: (cb: () => void) => { finished: Promise<void> }
}

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Run a state change as a view transition, so screens crossfade and a tapped
 *  cover morphs into the next screen's hero instead of hard-cutting. */
export function transition(update: () => void, kind: 'push' | 'pop' | 'tab' = 'tab'): void {
  const doc = document as Doc
  if (!doc.startViewTransition || reduced()) {
    update()
    return
  }
  // Which way the screen moves on a phone (UX-8): the CSS reads it.
  document.documentElement.dataset.nav = kind
  doc.startViewTransition(() => flushSync(update)).finished.finally(() => {
    delete document.documentElement.dataset.nav
  })
}

// The dock's destinations: moving between them is a crossfade, not a push.
const TABS = new Set(['/', '/bookings', '/inbox', '/earn', '/profile'])
const kindOf = (to: string | number): 'push' | 'pop' | 'tab' =>
  typeof to === 'number' ? (to < 0 ? 'pop' : 'push') : TABS.has(to.split(/[?#]/)[0]) ? 'tab' : 'push'

export function useNav() {
  const nav = useNavigate()
  return useCallback(
    (to: string | number, opts?: { replace?: boolean; state?: unknown }) => {
      transition(() => {
        if (typeof to === 'number') nav(to)
        else nav(to, { replace: opts?.replace, state: opts?.state })
      }, kindOf(to))
    },
    [nav],
  )
}

/** Back if there is somewhere to go back to; otherwise the fallback, replacing
 *  the entry so a deep link into a sheet does not strand anyone. */
export function useBack(fallback: string) {
  const nav = useNav()
  const { key } = useLocation()
  return useCallback(() => {
    if (key === 'default') nav(fallback, { replace: true })
    else nav(-1)
  }, [nav, key, fallback])
}

/* ------------------------------------------------------------------- hero */
// Which cover the detail grows out of. Exactly one element may carry the
// view-transition-name `hero` at a time, so the key names both the section and
// the listing, "rail:l1", and is set synchronously before the navigation so
// the browser's "before" snapshot already sees it.

let heroKey: string | null = null
const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const hero = {
  set(key: string | null) {
    heroKey = key
    listeners.forEach((fn) => fn())
  },
}

/** True when this element is the one that should morph. */
export function useIsHero(key: string): boolean {
  return useSyncExternalStore(subscribe, () => heroKey === key)
}

/** Name this card, then go, the two steps every "open" tap does. */
export function openFrom(key: string, go: () => void): void {
  flushSync(() => hero.set(key))
  go()
}

export const HERO_STYLE = { viewTransitionName: 'hero' } as const
