import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Booking, BookingStatus } from '../../domain/types.ts'
import { formatEur } from '../../domain/money.ts'
import { useBookings } from '../../data/repo.ts'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Button, EmptyState, Pill, Segmented, Skeleton } from '../components/ui.tsx'
import { range } from '../format.ts'

const LIVE: BookingStatus[] = ['awaiting_payment', 'requested', 'accepted', 'active', 'disputed']

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
    case 'disputed':
      return { label: 'Under review', tone: 'warn' }
  }
}

/** Soonest first for what is coming up; most recent first for what is past. */
const byStart = (a: Booking, b: Booking) => Date.parse(a.match.start) - Date.parse(b.match.start)

export function Bookings() {
  const nav = useNavigate()
  const session = useSession()
  const authReady = useAuthReady()
  const [params, setParams] = useSearchParams()
  // Both sides of the market in one place: what you booked, and what people booked from you.
  const role: 'requester' | 'owner' = params.get('as') === 'hosting' ? 'owner' : 'requester'
  const hosting = role === 'owner'
  const bookings = useBookings(role)
  // Both switches live in the URL, so back and a shared link keep them.
  const tab: 'live' | 'past' = params.get('tab') === 'past' ? 'past' : 'live'
  const setTab = (t: 'live' | 'past') => {
    const next = new URLSearchParams(params)
    if (t === 'past') next.set('tab', 'past')
    else next.delete('tab')
    setParams(next, { replace: true })
  }

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

  const mine = bookings.data?.items ?? []
  const live = mine.filter((b) => LIVE.includes(b.status)).sort(byStart)
  const past = mine.filter((b) => !LIVE.includes(b.status)).sort((a, b) => byStart(b, a))
  const shown = tab === 'live' ? live : past

  return (
    <Screen
      title="Bookings"
      sub={hosting ? 'People booking what you listed.' : 'Capacity you have taken from other people.'}
    >
      <div className="pb-4">
        <Segmented
          label="Whose bookings"
          value={role}
          onChange={(r) => setParams(r === 'owner' ? { as: 'hosting' } : {}, { replace: true })}
          options={[
            { value: 'requester', label: 'I booked' },
            { value: 'owner', label: "I'm hosting" },
          ]}
        />
      </div>
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
        hosting ? (
          <EmptyState
            icon="wallet"
            title="Nobody has booked you yet"
            body="Accepted requests show up here, with the time and who is coming."
            action={<Button to={'/earn'}>Go to Earn</Button>}
          />
        ) : (
          <EmptyState
            icon="ticket"
            title="No bookings yet"
            body="When you book someone's idle hour it shows up here. Once the owner accepts, you get the address and handover notes."
            action={<Button to={'/'}>Find something nearby</Button>}
          />
        )
      ) : shown.length === 0 ? (
        <EmptyState
          icon={tab === 'live' ? 'calendar' : 'clock'}
          title={tab === 'live' ? 'Nothing upcoming' : 'Nothing finished yet'}
          body={
            tab === 'live'
              ? 'Your past bookings are under the Past tab.'
              : 'Bookings move here once they are done, declined or cancelled.'
          }
          action={tab === 'live' ? <Button to={'/'}>Browse capacity</Button> : undefined}
        />
      ) : (
        <ul className="ruled border-t border-[var(--line)]">
          {shown.map((b) => (
            <li key={b.id}>
              <BookingRow booking={b} hosting={hosting} onOpen={() => nav(`/bookings/${b.id}`)} />
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}

function BookingRow({ booking, hosting, onOpen }: { booking: Booking; hosting: boolean; onOpen: () => void }) {
  const pill =
    hosting && booking.status === 'requested'
      ? { label: 'Needs your answer', tone: 'accent' as const }
      : hosting && booking.status === 'completed'
        ? { label: booking.outcome ? 'Rated' : 'Finished', tone: 'neutral' as const }
        : statusPill(booking.status, Boolean(booking.outcome))
  const dim = !LIVE.includes(booking.status) && booking.status !== 'completed'
  // What it looked like when it was booked, even if the listing has changed since.
  const title = booking.listing?.title ?? 'Listing removed'
  const photo = booking.listing?.photo
  const ownerName = hosting ? 'You are hosting' : (booking.listing?.ownerName ?? '')

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
        thumb
        className={`w-[58px] shrink-0 rounded-[var(--radius-plate)] ${dim ? 'opacity-40 grayscale' : ''}`}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-3">
          <span className={`truncate text-[15.5px] font-semibold ${dim ? 'text-[var(--ink-3)]' : ''}`}>
            {title}
          </span>
          <span className="tnum shrink-0 text-[15.5px] font-bold">
            {formatEur(hosting ? booking.match.quote.ownerNet : booking.match.quote.total)}
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
