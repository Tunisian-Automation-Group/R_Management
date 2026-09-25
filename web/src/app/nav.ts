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
export function transition(update: () => void): void {
  const doc = document as Doc
  if (!doc.startViewTransition || reduced()) {
    update()
    return
  }
  doc.startViewTransition(() => flushSync(update))
}

export function useNav() {
  const nav = useNavigate()
  return useCallback(
    (to: string | number, opts?: { replace?: boolean }) => {
      transition(() => {
        if (typeof to === 'number') nav(to)
        else nav(to, { replace: opts?.replace })
      })
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
