import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Booking, BookingStatus } from '../../domain/types.ts'
import { formatMoney } from '../../domain/money.ts'
import { moved } from '../../domain/pricing.ts'
import { useBookings } from '../../data/repo.ts'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Button, Card, EmptyState, Pill, Segmented, Skeleton } from '../components/ui.tsx'
import { range, relative } from '../format.ts'
import { t } from '../../i18n.ts'

const LIVE: BookingStatus[] = ['awaiting_payment', 'requested', 'accepted', 'active', 'disputed']

const statusPill = (
  status: BookingStatus,
  rated: boolean,
): { label: string; tone: 'neutral' | 'accent' | 'success' | 'warn' | 'danger' } => {
  switch (status) {
    case 'awaiting_payment':
      return { label: t('Authorising payment'), tone: 'warn' }
    case 'requested':
      return { label: t('Waiting for reply'), tone: 'warn' }
    case 'accepted':
      return { label: t('Confirmed'), tone: 'success' }
    case 'active':
      return { label: t('In progress'), tone: 'success' }
    case 'completed':
      return rated ? { label: t('Rated'), tone: 'neutral' } : { label: t('Rate it'), tone: 'accent' }
    case 'declined':
      return { label: t('Declined'), tone: 'danger' }
    case 'cancelled':
      return { label: t('Cancelled'), tone: 'neutral' }
    case 'expired':
      return { label: t('Expired'), tone: 'neutral' }
    case 'payment_failed':
      return { label: t('Payment failed'), tone: 'danger' }
    case 'disputed':
      return { label: t('Under review'), tone: 'warn' }
  }
}

/** The one booking that needs this person now, and what to do about it (U-37). */
function nextUp(all: Booking[], hosting: boolean): { booking: Booking; action: string } | null {
  const soonest = (bs: Booking[]) => [...bs].sort(byStart)[0]
  const find = (status: BookingStatus, extra: (b: Booking) => boolean = () => true) =>
    soonest(all.filter((b) => b.status === status && extra(b)))
  const pairs: [Booking | undefined, string][] = hosting
    ? [
        [find('requested'), t('Answer this request before it expires')],
        [find('active'), t('In progress now')],
        [find('accepted'), t('Next hand-over {when}')],
      ]
    : [
        [find('awaiting_payment'), t('Finish paying so the owner is asked')],
        [find('active'), t('In progress now')],
        [find('accepted'), t('Next hand-over {when}')],
        [find('completed', (b) => !b.outcome), t('Rate how it went')],
      ]
  const hit = pairs.find(([b]) => b)
  if (!hit?.[0]) return null
  return { booking: hit[0], action: hit[1].replace('{when}', relative(hit[0].match.start)) }
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
  const setTab = (to: 'live' | 'past') => {
    const next = new URLSearchParams(params)
    if (to === 'past') next.set('tab', 'past')
    else next.delete('tab')
    setParams(next, { replace: true })
  }

  if (!authReady || (session && bookings.isPending)) {
    return (
      <Screen title={t('Bookings')}>
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
      <Screen title={t('Bookings')} sub={t('Capacity you have taken from other people.')}>
        <SignedOut what={t('see your bookings')} next="/bookings" />
      </Screen>
    )
  }

  const mine = bookings.data?.items ?? []
  const live = mine.filter((b) => LIVE.includes(b.status)).sort(byStart)
  const past = mine.filter((b) => !LIVE.includes(b.status)).sort((a, b) => byStart(b, a))
  const shown = tab === 'live' ? live : past
  const next = nextUp(mine, hosting)

  return (
    <Screen
      title={t('Bookings')}
      sub={hosting ? t('People booking what you listed.') : t('Capacity you have taken from other people.')}
    >
      <div className="pb-4">
        <Segmented
          label={t('Whose bookings')}
          value={role}
          onChange={(r) => setParams(r === 'owner' ? { as: 'hosting' } : {}, { replace: true })}
          options={[
            { value: 'requester', label: t('I booked') },
            { value: 'owner', label: t("I'm hosting") },
          ]}
        />
      </div>
      {mine.length > 0 && (
        <div className="pb-5">
          <Segmented
            label={t('Booking state')}
            value={tab}
            onChange={setTab}
            options={[
              { value: 'live', label: `${t('Upcoming')}${live.length ? ` (${live.length})` : ''}` },
              { value: 'past', label: t('Past') },
            ]}
          />
        </div>
      )}

      {/* An unrated finished booking is past: its prompt lives on the Past tab,
          never above "Nothing upcoming" (V3-11). */}
      {next && LIVE.includes(next.booking.status) === (tab === 'live') && (
        <Card className="mb-5 flex gap-4 p-5">
          <Photo
            src={next.booking.listing?.photo}
            alt=""
            categoryId={next.booking.requirement.category}
            aspect={1}
            className="w-[64px] shrink-0 rounded-[14px]"
          />
          <div className="min-w-0 flex-1">
            <p className="t-label mb-1">{t('Next up')}</p>
            <p className="truncate text-[1rem] font-semibold">{next.booking.listing?.title ?? t('Listing removed')}</p>
            <p className="t-sm tnum text-[var(--ink-3)]">{range(next.booking.match.start, next.booking.match.end)}</p>
            <p className="t-sm mt-1 font-semibold text-[var(--ink-2)]">{next.action}</p>
            <Button size="sm" className="mt-3" onClick={() => nav(`/bookings/${next.booking.id}`)}>
              {t('Open booking')}
            </Button>
          </div>
        </Card>
      )}

      {mine.length === 0 ? (
        hosting ? (
          <EmptyState
            icon="wallet"
            title={t('Nobody has booked you yet')}
            body={t('Accepted requests show up here, with the time and who is coming.')}
            action={<Button to={'/earn'}>{t('Go to Earn')}</Button>}
          />
        ) : (
          <EmptyState
            icon="ticket"
            title={t('No bookings yet')}
            body={t("When you book someone's idle hour it shows up here. Once the owner accepts, you get the address and handover notes.")}
            action={<Button to={'/'}>{t('Find something nearby')}</Button>}
          />
        )
      ) : shown.length === 0 ? (
        <EmptyState
          icon={tab === 'live' ? 'calendar' : 'clock'}
          title={tab === 'live' ? t('Nothing upcoming') : t('Nothing finished yet')}
          body={
            tab === 'live'
              ? t('Your past bookings are under the Past tab.')
              : t('Bookings move here once they are done, declined or cancelled.')
          }
          action={tab === 'live' ? <Button to={'/'}>{t('Browse capacity')}</Button> : undefined}
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
      ? { label: t('Needs your answer'), tone: 'accent' as const }
      : hosting && booking.status === 'completed'
        ? { label: booking.outcome ? t('Rated') : t('Finished'), tone: 'neutral' as const }
        : statusPill(booking.status, Boolean(booking.outcome))
  const dim = !LIVE.includes(booking.status) && booking.status !== 'completed'
  // What it looked like when it was booked, even if the listing has changed since.
  const title = booking.listing?.title ?? t('Listing removed')
  const photo = booking.listing?.photo
  const ownerName = hosting ? t('You are hosting') : (booking.listing?.ownerName ?? '')

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
          <span className={`truncate text-[0.9688rem] font-semibold ${dim ? 'text-[var(--ink-3)]' : ''}`}>
            {title}
          </span>
          <span className="tnum shrink-0 text-[0.9688rem] font-bold">
            {formatMoney(amountOf(booking, hosting), booking.currency ?? booking.match.quote.currency)}
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

/** The price, or once money came back (a refund, a partial settlement) what
 *  really stayed: the renter's net cost, the owner's share of it (V7-3). */
function amountOf(b: Booking, hosting: boolean): number {
  if (b.charged === undefined && b.refundAmount === undefined && b.noShow !== 'renter') return hosting ? b.match.quote.ownerNet : b.match.quote.total
  const m = moved(b)
  // Everything back (or nothing taken): the price, as for any ended booking; its status says the rest.
  if (m.charged - m.refunded <= 0) return hosting ? b.match.quote.ownerNet : b.match.quote.total
  return hosting ? m.ownerNet : m.charged - m.refunded
}
