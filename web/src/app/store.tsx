// Client-only state: what the person is searching for, and the toast. Every
// piece of server data lives in the query cache (data/repo.ts), and who is
// signed in lives in data/auth.ts.
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from 'react'
import type { CategoryId, Requirement } from '../domain/types.ts'
import { category } from '../domain/categories.ts'
import { useSession } from '../data/auth.ts'
import { t } from '../i18n.ts'

export type Search = {
  /** Where the user is searching from. A district name. */
  district: string
  /** True once the person picked it, so their home district no longer overrides it. */
  districtChosen: boolean
  categoryId: CategoryId | null
  /** Window mode: how long you want it. */
  hours: number
  /** Batch mode: how many you need. */
  quantity: number
  maxDistanceKm: number
  /** How far out you are willing to look. */
  withinDays: number
  query: string
}

export type Tone = 'ok' | 'error'
export type State = { search: Search; toast: { message: string; tone: Tone } | null }

export type Event =
  | { type: 'SEARCH_CHANGED'; patch: Partial<Search> }
  | { type: 'TOAST'; message: string; tone?: Tone }
  | { type: 'TOAST_CLEARED' }

/**
 * One radius for everyone: 75 km covers a city and its industrial belt. The
 * district is a placeholder until `GET /me` says where this person starts.
 */
export const defaultSearch: Search = {
  district: 'Kreuzberg',
  districtChosen: false,
  categoryId: null,
  hours: 4,
  quantity: 50,
  maxDistanceKm: 75,
  withinDays: 14,
  query: '',
}

export function reduce(state: State, e: Event): State {
  switch (e.type) {
    case 'SEARCH_CHANGED': {
      const search = { ...state.search, ...e.patch }
      // Carrying the last duration into a new category produces guaranteed-empty
      // searches. Adopt the category's own first option.
      const pickedCategory = e.patch.categoryId !== undefined && e.patch.categoryId !== state.search.categoryId
      if (pickedCategory && search.categoryId) {
        const meta = category(search.categoryId)
        if (meta.mode === 'window' && meta.quickHours?.length && e.patch.hours === undefined) {
          search.hours = meta.quickHours[0]
        }
      }
      return { ...state, search }
    }
    case 'TOAST':
      return { ...state, toast: { message: e.message, tone: e.tone ?? 'ok' } }
    case 'TOAST_CLEARED':
      return { ...state, toast: null }
    default:
      return state
  }
}

const Ctx = createContext<{ state: State; send: (e: Event) => void } | null>(null)

const CITY_KEY = 'cappy.district.v1'

/** Where this device last chose to search from: a convenience, so a reload does not reset it. */
function chosenDistrict(): Partial<Search> {
  try {
    const d = localStorage.getItem(CITY_KEY)
    return d ? { district: d, districtChosen: true } : {}
  } catch {
    return {}
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, undefined, () => ({
    search: { ...defaultSearch, ...chosenDistrict() },
    toast: null,
  }))
  const send = useCallback((e: Event) => dispatch(e), [])
  const session = useSession()

  useEffect(() => {
    if (!state.search.districtChosen) return
    try {
      localStorage.setItem(CITY_KEY, state.search.district)
    } catch {
      // Storage blocked: the choice lasts this page load.
    }
  }, [state.search.district, state.search.districtChosen])

  // Signing out forgets the person's home district (it was theirs, not the
  // device's); a city picked by hand stays.
  const signedIn = Boolean(session)
  useEffect(() => {
    if (!signedIn && !state.search.districtChosen) {
      dispatch({ type: 'SEARCH_CHANGED', patch: { district: defaultSearch.district } })
    }
  }, [signedIn, state.search.districtChosen])
  const value = useMemo(() => ({ state, send }), [state, send])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useCappy() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useCappy used outside AppProvider')
  return ctx
}

/** Show a message briefly. `error` says something failed: no tick (V4-4). */
export function useToast(): (message: string, tone?: Tone) => void {
  const { send } = useCappy()
  return useCallback((message: string, tone?: Tone) => send({ type: 'TOAST', message, tone }), [send])
}

/** The signed-in person's id (their Cognito sub), or '' when nobody is. */
export function useMe(): string {
  return useSession()?.sub ?? ''
}

/** Say what went wrong in words a person can act on. */
export const messageOf = (err: unknown) =>
  err instanceof Error && err.message ? err.message : t('Something went wrong. Please try again.')

/** The search turned into something the matcher understands. */
export function buildRequirement(search: Search, now: Date): Requirement | null {
  if (!search.categoryId) return null
  const meta = category(search.categoryId)
  const until = new Date(now.getTime() + search.withinDays * 86_400_000).toISOString()
  if (meta.mode === 'window') {
    return {
      mode: 'window',
      category: search.categoryId,
      hours: search.hours,
      earliest: now.toISOString(),
      latest: until,
      district: search.district,
      maxDistanceKm: search.maxDistanceKm,
    }
  }
  return {
    mode: 'batch',
    category: search.categoryId,
    quantity: search.quantity,
    deadline: until,
    district: search.district,
    maxDistanceKm: search.maxDistanceKm,
  }
}
