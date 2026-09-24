import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { AppProvider, ME, useCappy } from './store.tsx'
import { Dock } from './components/AppShell.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { Banner, Button, Toast } from './components/ui.tsx'
import { Browse } from './screens/Browse.tsx'
import { Listing } from './screens/Listing.tsx'
import { Bookings } from './screens/Bookings.tsx'
import { BookingDetail } from './screens/BookingDetail.tsx'
import { Earn } from './screens/Earn.tsx'
import { AddListing } from './screens/AddListing.tsx'
import { Profile } from './screens/Profile.tsx'

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

  // Each side of the market counts what is waiting on this person, separately,
  // requests to answer as a host, and finished bookings still to rate as a guest.
  const badges: Record<string, number> = {
    '/earn': state.bookings.filter((b) => b.match.ownerId === ME && b.status === 'requested')
      .length,
    '/bookings': state.bookings.filter(
      (b) => b.match.ownerId !== ME && b.status === 'completed' && !b.outcome,
    ).length,
  }

  return (
    <>
      <ScrollReset />
      {state.loadError && !state.ready && (
        <div className="mx-auto w-full max-w-[560px] px-5 pt-5 md:max-w-[760px]">
          <Banner
            tone="danger"
            title="Cappy is not reachable right now"
            body={state.loadError}
            action={
              <Button size="sm" onClick={() => send({ type: 'LOAD_RETRY' })}>
                Try again
              </Button>
            }
          />
        </div>
      )}
      <Routes>
        <Route path="/" element={<Browse />} />
        <Route path="/listing/:id" element={<Listing />} />
        <Route path="/bookings" element={<Bookings />} />
        <Route path="/bookings/:id" element={<BookingDetail />} />
        <Route path="/earn" element={<Earn />} />
        <Route path="/earn/new" element={<AddListing />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Dock badges={badges} />
      {state.toast && (
        <Toast message={state.toast} onDone={() => send({ type: 'TOAST_CLEARED' })} />
      )}
    </>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppProvider>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </AppProvider>
    </ErrorBoundary>
  )
}
