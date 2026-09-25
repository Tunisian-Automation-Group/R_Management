import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { AppProvider, useCappy } from './store.tsx'
import { APP_VERSION, queryClient, useAppConfig, useBookings, useMeQuery, versionBelow } from '../data/repo.ts'
import { useSession } from '../data/auth.ts'
import { Dock } from './components/AppShell.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { Toast } from './components/ui.tsx'
import { Browse } from './screens/Browse.tsx'
import { Listing } from './screens/Listing.tsx'
import { Bookings } from './screens/Bookings.tsx'
import { BookingDetail } from './screens/BookingDetail.tsx'
import { Earn } from './screens/Earn.tsx'
import { AddListing } from './screens/AddListing.tsx'
import { Profile } from './screens/Profile.tsx'
import { Login } from './screens/Login.tsx'
import { Onboarding } from './screens/Onboarding.tsx'
import { AccountDeletion, Legal } from './screens/Legal.tsx'
import { Admin } from './screens/Admin.tsx'
import { NotFound } from './screens/NotFound.tsx'
import { Screen } from './components/AppShell.tsx'
import { t, useLang } from '../i18n.ts'

/** A new screen starts at the top, the way a native push does. */
function ScrollReset() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

function Shell() {
  const { state, send } = useCappy()
  const session = useSession()
  const me = useMeQuery()
  const hosting = useBookings('owner')
  const booked = useBookings('requester')

  // Searches start where this person is, until they pick somewhere else.
  const home = me.data?.homeDistrict
  useEffect(() => {
    if (home && !state.search.districtChosen) send({ type: 'SEARCH_CHANGED', patch: { district: home } })
  }, [home, state.search.districtChosen, send])

  // What is waiting on this person: requests to answer, bookings to rate.
  const badges: Record<string, number> = {
    '/earn': hosting.data?.items.filter((b) => b.status === 'requested').length ?? 0,
    '/bookings': booked.data?.items.filter((b) => b.status === 'completed' && !b.outcome).length ?? 0,
  }

  // Signed in with no profile yet: that comes first, whatever the route.
  const needsProfile = Boolean(session && me.data && !me.data.owner)

  // An App Store / Google Play build older than the API supports: nothing else is
  // safe to show. The web is always the current build, so it is never gated.
  const config = useAppConfig()
  if (NATIVE && config.data && versionBelow(APP_VERSION, config.data.minVersion)) return <UpdateRequired />

  return (
    <>
      <ScrollReset />
      {/* Keyboard users skip the navigation; the nav comes first in the page. */}
      <a
        href="#main"
        className="sr-only z-[70] rounded-[var(--radius-control)] bg-[var(--field)] px-4 py-3 text-[14px] font-semibold text-[var(--on-field)]
          focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t('Skip to content')}
      </a>
      <Dock badges={badges} />
      {needsProfile ? (
        <Onboarding />
      ) : (
        <Routes>
          <Route path="/" element={<Browse />} />
          <Route path="/listing/:id" element={<Listing />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/bookings/:id" element={<BookingDetail />} />
          <Route path="/earn" element={<Earn />} />
          <Route path="/earn/new" element={<AddListing />} />
          <Route path="/earn/edit/:id" element={<AddListing />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/login" element={<Login />} />
          <Route path="/legal/:page" element={<Legal />} />
          <Route path="/account/delete" element={<AccountDeletion />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      )}
      {state.toast && <Toast message={state.toast} onDone={() => send({ type: 'TOAST_CLEARED' })} />}
    </>
  )
}

/** Inside the Capacitor shell (ADR 0012), not a browser. */
const NATIVE = Boolean(
  (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.(),
)

function UpdateRequired() {
  return (
    <Screen title={t('Update Cappy')} docTitle={t('Update required')}>
      <p className="t-body max-w-[46ch] text-[var(--ink-2)]">
        {t(
          'This version of the app is too old to talk to Cappy safely. Update it from the App Store or Google Play to carry on; your bookings and listings are all there.',
        )}
      </p>
      <StoreLinks />
    </Screen>
  )
}

/** Where the update is. The store URLs come from the build (VITE_APP_STORE_URL,
 *  VITE_PLAY_STORE_URL); a shell only shows the one for its own platform. */
function StoreLinks() {
  const platform = (window as unknown as { Capacitor?: { getPlatform?: () => string } }).Capacitor?.getPlatform?.()
  const ios = import.meta.env.VITE_APP_STORE_URL as string | undefined
  const android = import.meta.env.VITE_PLAY_STORE_URL as string | undefined
  const url = platform === 'ios' ? ios : platform === 'android' ? android : (ios ?? android)
  if (!url) return null
  return (
    <a href={url} className="mt-6 inline-flex rounded-[var(--radius-control)] bg-[var(--field)] px-5 py-3 font-semibold text-[var(--on-field)]">
      {t('Update now')}
    </a>
  )
}

export default function App() {
  // A new language remounts everything below, so every string re-renders
  // (the query cache sits above and survives).
  const lang = useLang()
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppProvider key={lang}>
          <BrowserRouter>
            <Shell />
          </BrowserRouter>
        </AppProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
