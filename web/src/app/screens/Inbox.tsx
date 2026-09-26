// Inbox (UX-12): every conversation, across bookings on both sides, newest
// first, with an unread dot. A thread opens on its booking, where the booking
// card sits above the chat.
//
// ponytail: built from the existing booking and message lists, reading the
// newest 20 bookings' threads, and "read" is remembered on this device. The
// server should offer GET /api/inbox?cursor= → [{bookingId, otherName,
// listingTitle, photo, status, lastMessage {body, at, mine}, unread}] with
// read receipts, and then this screen needs one query.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Booking } from '../../domain/types.ts'
import { useBookings, useMessages } from '../../data/repo.ts'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { EmptyState, Pill, Segmented, Skeleton } from '../components/ui.tsx'
import { ago } from '../format.ts'
import { lastSeen } from '../seen.ts'
import { statusPill } from './Bookings.tsx'
import { t } from '../../i18n.ts'

const THREADS = 20
const QUIET: Booking['status'][] = ['awaiting_payment', 'payment_failed']

export function Inbox() {
  const booked = useBookings('requester')
  const hosting = useBookings('owner')
  const [tab, setTab] = useState<'all' | 'unread'>('all')
  const [unread, setUnread] = useState<Record<string, boolean>>({})
  const [empty, setEmpty] = useState<Record<string, boolean>>({})

  const threads = useMemo(() => {
    const rows = [
      ...(booked.data?.items ?? []).map((b) => ({ b, hosting: false })),
      ...(hosting.data?.items ?? []).map((b) => ({ b, hosting: true })),
    ].filter(({ b }) => !QUIET.includes(b.status))
    return rows.sort((x, y) => Date.parse(y.b.createdAt) - Date.parse(x.b.createdAt)).slice(0, THREADS)
  }, [booked.data, hosting.data])

  const loading = booked.isPending || hosting.isPending
  const shown = threads.filter(({ b }) => !empty[b.id] && (tab === 'all' || unread[b.id]))

  return (
    <Screen title={t('Inbox')}>
      <Segmented
        label={t('Inbox')}
        value={tab}
        onChange={setTab}
        options={[
          { value: 'all', label: t('All') },
          { value: 'unread', label: t('Unread') },
        ]}
      />
      {loading ? (
        <div className="mt-4 space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <ul className="ruled mt-2">
          {threads.map(({ b, hosting }) => (
            <ThreadRow
              key={b.id}
              booking={b}
              hosting={hosting}
              hidden={!shown.some((s) => s.b.id === b.id)}
              onState={(u, e) => {
                setUnread((m) => (m[b.id] === u ? m : { ...m, [b.id]: u }))
                setEmpty((m) => (m[b.id] === e ? m : { ...m, [b.id]: e }))
              }}
            />
          ))}
        </ul>
      )}
      {!loading && shown.length === 0 && (
        <EmptyState
          icon="chat"
          title={tab === 'unread' ? t('Nothing unread') : t('No messages yet')}
          body={t('Messages about a booking appear here, for what you booked and for what people booked from you.')}
        />
      )}
    </Screen>
  )
}

function ThreadRow({
  booking,
  hosting,
  hidden,
  onState,
}: {
  booking: Booking
  hosting: boolean
  hidden: boolean
  onState: (unread: boolean, empty: boolean) => void
}) {
  const nav = useNavigate()
  const messages = useMessages(booking.id, booking.status)
  const items = messages.data?.items ?? []
  const last = items[items.length - 1]
  const unread = Boolean(last && !last.mine && Date.parse(last.at) > lastSeen(booking.id))
  const loaded = Boolean(messages.data)
  const report = useRef(onState)
  report.current = onState
  useEffect(() => {
    if (loaded) report.current(unread, !last)
  }, [loaded, unread, last])
  if (hidden || !last) return null
  const pill = statusPill(booking.status, Boolean(booking.outcome))
  const who = hosting ? t('Your renter') : (booking.listing?.ownerName ?? '')
  return (
    <li>
      <button
        type="button"
        onClick={() => nav(`/bookings/${booking.id}#messages`)}
        className="press-soft flex w-full items-center gap-3.5 py-4 text-left"
      >
        <Photo src={booking.listing?.photo} alt="" categoryId={booking.requirement.category} aspect={1} thumb width={52} className="w-[52px] shrink-0 rounded-[var(--radius-m)]" />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className={`truncate text-body ${unread ? 'font-bold' : 'font-semibold'}`}>{who}</span>
            <span className="tnum shrink-0 text-label text-[var(--ink-4)]">{ago(last.at)}</span>
          </span>
          <span className="t-sm block truncate text-[var(--ink-3)]">{booking.listing?.title ?? t('Listing removed')}</span>
          <span className={`t-sm mt-0.5 block truncate ${unread ? 'text-[var(--ink)]' : 'text-[var(--ink-3)]'}`}>
            {last.mine ? `${t('You')}: ` : ''}
            {last.body}
          </span>
          <span className="mt-2 flex items-center gap-2">
            <Pill tone={pill.tone}>{pill.label}</Pill>
            {unread && <span className="h-2 w-2 rounded-full bg-[var(--badge)]" aria-label={t('Unread')} />}
          </span>
        </span>
      </button>
    </li>
  )
}
