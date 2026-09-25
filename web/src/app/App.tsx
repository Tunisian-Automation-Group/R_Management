import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { AppProvider, useCappy } from './store.tsx'
import { queryClient, useBookings, useMeQuery } from '../data/repo.ts'
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

  return (
    <>
      <ScrollReset />
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
          <Route path="/profile" element={<Profile />} />
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
      <Dock badges={badges} />
      {state.toast && <Toast message={state.toast} onDone={() => send({ type: 'TOAST_CLEARED' })} />}
    </>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <BrowserRouter>
            <Shell />
          </BrowserRouter>
        </AppProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
