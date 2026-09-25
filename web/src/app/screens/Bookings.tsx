import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Booking, BookingStatus } from '../../domain/types.ts'
import { formatEur } from '../../domain/money.ts'
import { useBookings } from '../../data/repo.ts'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Button, EmptyState, Pill, Segmented, Skeleton } from '../components/ui.tsx'
import { range } from '../format.ts'

const LIVE: BookingStatus[] = ['awaiting_payment', 'requested', 'accepted', 'active']

const statusPill = (
  status: BookingStatus,
  rated: boolean,
): { label: string; tone: 'neutral' | 'accent' | 'success' | 'warn' | 'danger' } => {
  switch (status) {
    case 'awaiting_payment':
      return { label: 'Authorising payment', tone: 'warn' }
    case 'requested':
      return { label: 'Waiting for reply', tone: 'warn' }
    case 'accepted':
      return { label: 'Confirmed', tone: 'success' }
    case 'active':
      return { label: 'In progress', tone: 'success' }
    case 'completed':
      return rated ? { label: 'Rated', tone: 'neutral' } : { label: 'Rate it', tone: 'accent' }
    case 'declined':
      return { label: 'Declined', tone: 'danger' }
    case 'cancelled':
      return { label: 'Cancelled', tone: 'neutral' }
    case 'expired':
      return { label: 'Expired', tone: 'neutral' }
    case 'payment_failed':
      return { label: 'Payment failed', tone: 'danger' }
  }
}

export function Bookings() {
  const nav = useNavigate()
  const session = useSession()
  const authReady = useAuthReady()
  const bookings = useBookings('requester')
  const [tab, setTab] = useState<'live' | 'past'>('live')

  if (!authReady || (session && bookings.isPending)) {
    return (
      <Screen title="Bookings">
        <div className="space-y-3 pt-2">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-[104px] rounded-[var(--radius-card)]" />
          ))}
        </div>
      </Screen>
    )
  }

  if (!session) {
    return (
      <Screen title="Bookings" sub="Capacity you have taken from other people.">
        <SignedOut what="see your bookings" next="/bookings" />
      </Screen>
    )
  }

  // Things you booked from other people. What you host lives under Earn.
  const mine = bookings.data?.items ?? []
  const live = mine.filter((b) => LIVE.includes(b.status))
  const past = mine.filter((b) => !LIVE.includes(b.status))
  const shown = tab === 'live' ? live : past

  return (
    <Screen
      title="Bookings"
      sub="Capacity you have taken from other people."
    >
      {mine.length > 0 && (
        <div className="pb-5">
          <Segmented
            label="Booking state"
            value={tab}
            onChange={setTab}
            options={[
              { value: 'live', label: `Upcoming${live.length ? ` (${live.length})` : ''}` },
              { value: 'past', label: 'Past' },
            ]}
          />
        </div>
      )}

      {mine.length === 0 ? (
        <EmptyState
          icon="ticket"
          title="No bookings yet"
          body="When you book someone's idle hour it shows up here, with the address and handover notes."
          action={<Button onClick={() => nav('/')}>Find something nearby</Button>}
        />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={tab === 'live' ? 'calendar' : 'clock'}
          title={tab === 'live' ? 'Nothing upcoming' : 'Nothing finished yet'}
          body={
            tab === 'live'
              ? 'Your past bookings are under the Past tab.'
              : 'Bookings move here once they are done, declined or cancelled.'
          }
          action={tab === 'live' ? <Button onClick={() => nav('/')}>Browse capacity</Button> : undefined}
        />
      ) : (
        <ul className="ruled border-t border-[var(--line)]">
          {shown.map((b) => (
            <li key={b.id}>
              <BookingRow booking={b} onOpen={() => nav(`/bookings/${b.id}`)} />
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}

function BookingRow({ booking, onOpen }: { booking: Booking; onOpen: () => void }) {
  const pill = statusPill(booking.status, Boolean(booking.outcome))
  const dim = !LIVE.includes(booking.status) && booking.status !== 'completed'
  // What it looked like when it was booked, even if the listing has changed since.
  const title = booking.listing?.title ?? 'Listing removed'
  const photo = booking.listing?.photo
  const ownerName = booking.listing?.ownerName ?? ''

  return (
    <button
      onClick={onOpen}
      className="flex w-full items-center gap-4 py-4 text-left transition-opacity duration-[160ms] hover:opacity-70"
    >
      {/* The same photograph as the card it came from, so a booking still looks
          like the thing you booked. */}
      <Photo
        src={photo}
        alt={title}
        categoryId={booking.requirement.category}
        aspect={1}
        className={`w-[58px] shrink-0 rounded-[var(--radius-plate)] ${dim ? 'opacity-40 grayscale' : ''}`}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-3">
          <span className={`truncate text-[15.5px] font-semibold ${dim ? 'text-[var(--ink-3)]' : ''}`}>
            {title}
          </span>
          <span className="tnum shrink-0 text-[15.5px] font-bold">
            {formatEur(booking.match.quote.total)}
          </span>
        </span>
        <span className="t-sm mt-0.5 block truncate text-[var(--ink-3)]">{ownerName}</span>
        <span className="t-sm tnum mt-0.5 block truncate text-[var(--ink-3)]">
          {range(booking.match.start, booking.match.end)}
        </span>
        <span className="mt-2 block">
          <Pill tone={pill.tone}>{pill.label}</Pill>
        </span>
      </span>
    </button>
  )
}
