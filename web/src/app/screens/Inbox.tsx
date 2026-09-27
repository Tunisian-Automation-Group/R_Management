// Inbox (UX-12): every conversation, across bookings on both sides, newest
// first, with an unread dot. The server keeps the read receipts (GET /api/inbox),
// so a thread read on the phone is read on the desktop too. A thread opens on
// its booking, where the booking card sits above the chat.
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { HIDDEN_CONTACT, useBooking, useBookings, useInbox, useOwner, type InboxItem } from '../../data/repo.ts'
import type { Booking } from '../../domain/types.ts'
import { Screen } from '../components/AppShell.tsx'
import { Conversation } from '../components/Conversation.tsx'
import { Photo } from '../components/Photo.tsx'
import { Avatar, Button, Card, DetailSkeleton, EmptyState, Pill, Segmented, Skeleton, TapLink } from '../components/ui.tsx'
import { ago, range } from '../format.ts'
import { statusPill } from './Bookings.tsx'
import { t } from '../../i18n.ts'

export function Inbox() {
  const inbox = useInbox()
  const [tab, setTab] = useState<'all' | 'unread'>('all')
  // A request opens a thread before anyone writes (UX-52): live bookings with no
  // message yet join the list with a first line that says what happened.
  const mine = useBookings('requester').data?.items ?? []
  const theirs = useBookings('owner').data?.items ?? []
  const known = new Set((inbox.data?.items ?? []).map((i) => i.bookingId))
  const quiet: InboxItem[] = [...mine.map((b) => [b, false] as const), ...theirs.map((b) => [b, true] as const)]
    .filter(([b]) => OPEN_THREAD.has(b.status) && !known.has(b.id))
    .map(([b, hosting]) => systemItem(b, hosting))
  const all = [...(inbox.data?.items ?? []), ...quiet].sort((x, y) => Date.parse(y.lastMessage.at) - Date.parse(x.lastMessage.at))
  const shown = all.filter((i) => tab === 'all' || i.unread)

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
      {inbox.isPending ? (
        <div className="mt-4 space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <ul className="ruled mt-2">
          {shown.map((i) => (
            <ThreadRow key={i.bookingId} item={i} />
          ))}
        </ul>
      )}
      {!inbox.isPending && shown.length === 0 && (
        <EmptyState
          icon="chat"
          title={tab === 'unread' ? t('Nothing unread') : t('No messages yet')}
          body={t('Messages about a booking appear here, for what you booked and for what people booked from you.')}
          action={
            tab === 'all' ? (
              <Button variant="secondary" to="/">
                {t('Find something nearby')}
              </Button>
            ) : undefined
          }
        />
      )}
    </Screen>
  )
}

function ThreadRow({ item }: { item: InboxItem }) {
  // Whether the reader has rated comes from their own booking lists (cached,
  // shared with Bookings and Earn); unknown counts as rated, so the Inbox never
  // nags for a rating already given (V9-4).
  const asRenter = useBookings('requester').data?.items.find((b) => b.id === item.bookingId)
  const asOwner = useBookings('owner').data?.items.find((b) => b.id === item.bookingId)
  const rated = asRenter ? Boolean(asRenter.outcome) : asOwner ? asOwner.renterRating != null : true
  const pill = statusPill(item.status, rated)
  const category = (asRenter ?? asOwner)?.requirement.category
  return (
    <li>
      <TapLink to={`/inbox/${item.bookingId}`} className="press-soft flex w-full items-center gap-3.5 py-4 text-left">
        {item.photo || category ? (
          // No photo: the listing's category plate, never a grey box.
          <Photo src={item.photo} alt="" categoryId={category ?? 'workshop'} aspect={1} thumb width={52} className="w-[52px] shrink-0 rounded-[var(--radius-m)]" />
        ) : (
          <Avatar initials={initialsOf(item.otherName ?? t('Your renter'))} size={52} />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className={`[overflow-wrap:anywhere] text-body ${item.unread ? 'font-bold' : 'font-semibold'}`}>{item.otherName ?? t('Your renter')}</span>
            <span className="tnum shrink-0 text-label text-[var(--ink-4)]">{ago(item.lastMessage.at)}</span>
          </span>
          <span className="t-sm block [overflow-wrap:anywhere] text-[var(--ink-3)]">{item.listingTitle || t('Listing removed')}</span>
          {/* A preview: two lines, hidden contact details as one short mark; the thread has it all. */}
          <span className={`t-sm mt-0.5 line-clamp-2 [overflow-wrap:anywhere] ${item.unread ? 'text-[var(--ink)]' : 'text-[var(--ink-3)]'}`}>
            {item.lastMessage.mine ? `${t('You')}: ` : ''}
            {preview(item.lastMessage.body)}
          </span>
          <span className="mt-2 flex items-center gap-2">
            <Pill tone={pill.tone}>{pill.label}</Pill>
            {item.unread > 0 && <span className="h-2 w-2 rounded-full bg-[var(--badge)]" role="img" aria-label={t("Unread")} />}
          </span>
        </span>
      </TapLink>
    </li>
  )
}

const preview = (body: string) => body.split(HIDDEN_CONTACT).join('•••')
const initialsOf = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')

const OPEN_THREAD = new Set(['requested', 'accepted', 'active', 'disputed'])

/** A thread nobody has written in yet, from the booking itself. */
function systemItem(b: Booking, hosting: boolean): InboxItem {
  const when = range(b.match.start, b.match.end)
  return {
    bookingId: b.id,
    otherName: hosting ? undefined : b.listing?.ownerName,
    listingTitle: b.listing?.title ?? '',
    photo: b.listing?.photo,
    status: b.status,
    lastMessage: {
      body: hosting ? t('Asked for {when}', { when }) : t('You requested {when}', { when }),
      at: b.createdAt,
      mine: false,
    },
    unread: 0,
  }
}

/** One conversation (UX-52): the booking pinned on top, the messages below,
 *  the composer at the bottom. The dock steps aside here, as on any detail. */
export function Thread() {
  const { id } = useParams()
  const booking = useBooking(id)
  const b = booking.data
  const asOwner = Boolean(b?.requesterId)
  const other = useOwner(asOwner ? b?.requesterId : b?.match.ownerId)
  if (booking.isPending || other.isPending) return <Screen back="/inbox"><DetailSkeleton /></Screen>
  if (!b) return <Screen back="/inbox" title={t('Inbox')}><EmptyState icon="chat" title={t('This conversation is gone')} body={t('The booking it belonged to no longer exists.')} /></Screen>
  const name = other.data?.name ?? (asOwner ? t('Your renter') : b.listing?.ownerName ?? '')
  const rated = asOwner ? b.renterRating != null : Boolean(b.outcome)
  const pill = statusPill(b.status, rated)
  const dead = ['declined', 'cancelled', 'expired', 'payment_failed'].includes(b.status)
  return (
    <Screen back="/inbox" title={name} docTitle={t('Messages with {name}', { name })}>
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <Photo src={b.listing?.photo} alt="" categoryId={b.requirement.category} aspect={1} thumb width={56} className="w-[56px] shrink-0 rounded-[var(--radius-m)]" />
        <div className="min-w-0 flex-1">
          <p className="[overflow-wrap:anywhere] text-body font-semibold">{b.listing?.title ?? t('Listing removed')}</p>
          <p className="t-sm tnum [overflow-wrap:anywhere] text-[var(--ink-3)]">{range(b.match.start, b.match.end)}</p>
          <span className="mt-1.5 block">
            <Pill tone={pill.tone}>{pill.label}</Pill>
          </span>
        </div>
        {/* Under the booking on a phone, so the title keeps its width. */}
        <div className="w-full md:w-auto">
          <Button size="sm" variant="secondary" block to={`/bookings/${b.id}`}>
            {t('Open the booking')}
          </Button>
        </div>
      </Card>
      <Conversation
        bookingId={b.id}
        status={b.status}
        otherName={name}
        otherId={other.data?.id}
        accepted={['accepted', 'active', 'completed', 'disputed'].includes(b.status)}
        closed={dead || (b.status === 'completed' && Date.now() > Date.parse(b.match.end) + 14 * 86_400_000)}
      />
    </Screen>
  )
}
