import { BrowserRouter, Navigate, Route, Routes, useLocation, useSearchParams } from 'react-router-dom'
import { lazy, Suspense, useEffect, type ComponentType } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { AppProvider, useCappy } from './store.tsx'
import { APP_VERSION, queryClient, useAppConfig, useBookings, useMeQuery, useNotices, versionBelow } from '../data/repo.ts'
import { accessToken, useAuthReady, useSession } from '../data/auth.ts'
import { enablePush } from '../native.ts'
import { device } from './device.ts'
import { OfflineBar } from './components/Offline.tsx'
import { PushPrime } from './components/PushPrime.tsx'
import { Welcome } from './screens/Welcome.tsx'
import { Dock } from './components/AppShell.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { Toast } from './components/ui.tsx'
import { Browse } from './screens/Browse.tsx'
import { Listing } from './screens/Listing.tsx'
import { Bookings } from './screens/Bookings.tsx'
import { Login } from './screens/Login.tsx'
import { NotFound } from './screens/NotFound.tsx'
import { Screen } from './components/AppShell.tsx'
import { t, useLang } from '../i18n.ts'

/** A screen fetched when first opened (S-15): the first paint carries only
 *  the way in, browsing and a listing. */
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))
const Help = page(() => import('./screens/Help.tsx'), 'Help')
const Notifications = page(() => import('./screens/Notifications.tsx'), 'Notifications')
const Earn = page(() => import('./screens/Earn.tsx'), 'Earn')
const AddListing = page(() => import('./screens/AddListing.tsx'), 'AddListing')
const Profile = page(() => import('./screens/Profile.tsx'), 'Profile')
const Legal = page(() => import('./screens/Legal.tsx'), 'Legal')
const AccountDeletion = page(() => import('./screens/Legal.tsx'), 'AccountDeletion')
const Admin = page(() => import('./screens/Admin.tsx'), 'Admin')
const AdminCase = page(() => import('./screens/AdminCases.tsx'), 'AdminCase')
const AdminListing = page(() => import('./screens/AdminCases.tsx'), 'AdminListing')
const BookingDetail = page(() => import('./screens/BookingDetail.tsx'), 'BookingDetail')
const Onboarding = page(() => import('./screens/Onboarding.tsx'), 'Onboarding')

/** A new screen starts at the top, the way a native push does. */
function ScrollReset() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

/** What anyone may open signed out (GOAL 13): the way in, the law, and help.
 *  Everything else of the product is for members only, and the server agrees. */
const PUBLIC = [/^\/welcome$/, /^\/login$/, /^\/legal\//, /^\/account\/delete$/, /^\/help(\/|$)/]
const isPublic = (path: string) => PUBLIC.some((re) => re.test(path))

/** Where the app was opened: anything but `/` is a deep link, which skips the welcome. */
const LAUNCH = window.location.pathname

function PublicRoutes() {
  return (
    <Routes>
      <Route path="/welcome" element={<Welcome />} />
      <Route path="/login" element={<Login />} />
      <Route path="/legal/:page" element={<Legal />} />
      <Route path="/account/delete" element={<AccountDeletion />} />
      <Route path="/help" element={<Help />} />
      <Route path="/help/:topic" element={<Help />} />
    </Routes>
  )
}

/** Signed out: nothing of the product renders, so none of it is fetched. */
function Gate() {
  const { pathname, search } = useLocation()
  if (isPublic(pathname))
    return (
      <>
        <OfflineBar />
        <Suspense fallback={null}>
          <PublicRoutes />
        </Suspense>
        <Toasts />
      </>
    )
  const firstTime = !device().welcomeSeen && !device().signedInBefore && LAUNCH === '/'
  if (firstTime) return <Navigate to="/welcome" replace />
  const next = pathname + search
  return <Navigate to={next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`} replace />
}

function Toasts() {
  const { state, send } = useCappy()
  return state.toast ? <Toast message={state.toast.message} tone={state.toast.tone} onDone={() => send({ type: 'TOAST_CLEARED' })} /> : null
}

function Shell() {
  const session = useSession()
  const ready = useAuthReady()
  // An App Store / Google Play build older than the API supports: nothing else is
  // safe to show. The web is always the current build, so it is never gated.
  const config = useAppConfig()
  if (NATIVE && config.data && versionBelow(APP_VERSION, config.data.minVersion)) return <UpdateRequired />
  // Until a stored session is restored or found absent, show nothing rather
  // than flash the welcome at someone who is signed in.
  if (!ready) return null
  return session ? <Member /> : <Gate />
}

function Member() {
  const { state, send } = useCappy()
  const session = useSession()
  const me = useMeQuery()
  const hosting = useBookings('owner')
  const booked = useBookings('requester')
  const notices = useNotices()

  // Searches start where this person is, until they pick somewhere else.
  const home = me.data?.homeDistrict
  useEffect(() => {
    if (home && !state.search.districtChosen) send({ type: 'SEARCH_CHANGED', patch: { district: home } })
  }, [home, state.search.districtChosen, send])

  // What is waiting on this person: requests to answer, bookings to rate.
  const badges: Record<string, number> = {
    '/earn': hosting.data?.items.filter((b) => b.status === 'requested').length ?? 0,
    '/bookings': booked.data?.items.filter((b) => b.status === 'completed' && !b.outcome).length ?? 0,
    // On a phone the bell lives on the You tab; on a desktop, in the header.
    '/notifications': notices.data?.unread ?? 0,
  }

  // Already allowed on this device: keep the push token current. Asking waits
  // for a moment that explains itself (PushPrime, U-4).
  useEffect(() => {
    void enablePush(accessToken)
  }, [])

  // Signed in with no profile yet: that comes first, whatever the route.
  const needsProfile = Boolean(session && me.data && !me.data.owner)

  return (
    <>
      <ScrollReset />
      {/* Keyboard users skip the navigation; the nav comes first in the page. */}
      <a
        href="#main"
        className="sr-only z-[70] rounded-[var(--radius-control)] bg-[var(--field)] px-4 py-3 text-body font-semibold text-[var(--on-field)]
          focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t('Skip to content')}
      </a>
      <OfflineBar />
      <Dock badges={badges} />
      <Suspense fallback={null}>
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
          <Route path="/welcome" element={<Navigate to="/" replace />} />
          <Route path="/help" element={<Help />} />
          <Route path="/help/:topic" element={<Help />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/legal/:page" element={<Legal />} />
          <Route path="/account/delete" element={<AccountDeletion />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/admin/case/:id" element={<AdminCase />} />
          <Route path="/admin/listing/:id" element={<AdminListing />} />
          <Route path="/pay/return" element={<PayReturn />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      )}
      </Suspense>
      <PushPrime />
      <Toasts />
    </>
  )
}

/** Back from a bank's card check (U-7): Stripe adds `redirect_status`. The
 *  booking page then waits for the payment to be confirmed. */
function PayReturn() {
  const [params] = useSearchParams()
  const { send } = useCappy()
  const booking = params.get('booking')
  const failed = params.get('redirect_status') === 'failed'
  useEffect(() => {
    if (failed) send({ type: 'TOAST', message: t('The payment did not go through.') })
    if (booking) void queryClient.invalidateQueries({ queryKey: ['booking', booking] })
  }, [booking, failed, send])
  return <Navigate to={booking ? `/bookings/${encodeURIComponent(booking)}` : '/bookings'} replace />
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
