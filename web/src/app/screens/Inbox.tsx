// Inbox (UX-12): every conversation, across bookings on both sides, newest
// first, with an unread dot. The server keeps the read receipts (GET /api/inbox),
// so a thread read on the phone is read on the desktop too. A thread opens on
// its booking, where the booking card sits above the chat.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInbox, type InboxItem } from '../../data/repo.ts'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { EmptyState, Pill, Segmented, Skeleton } from '../components/ui.tsx'
import { ago } from '../format.ts'
import { statusPill } from './Bookings.tsx'
import { t } from '../../i18n.ts'

export function Inbox() {
  const inbox = useInbox()
  const [tab, setTab] = useState<'all' | 'unread'>('all')
  const shown = (inbox.data?.items ?? []).filter((i) => tab === 'all' || i.unread)

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
        />
      )}
    </Screen>
  )
}

function ThreadRow({ item }: { item: InboxItem }) {
  const nav = useNavigate()
  const pill = statusPill(item.status, false)
  return (
    <li>
      <button
        type="button"
        onClick={() => nav(`/bookings/${item.bookingId}#messages`)}
        className="press-soft flex w-full items-center gap-3.5 py-4 text-left"
      >
        {item.photo ? (
          <Photo src={item.photo} alt="" categoryId="workshop" aspect={1} thumb width={52} className="w-[52px] shrink-0 rounded-[var(--radius-m)]" />
        ) : (
          // No photo and no category in the thread: a plain tile, never a guessed plate.
          <span aria-hidden className="h-[52px] w-[52px] shrink-0 rounded-[var(--radius-m)] bg-[var(--sunken)]" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className={`truncate text-body ${item.unread ? 'font-bold' : 'font-semibold'}`}>{item.otherName ?? t('Your renter')}</span>
            <span className="tnum shrink-0 text-label text-[var(--ink-4)]">{ago(item.lastMessage.at)}</span>
          </span>
          <span className="t-sm block truncate text-[var(--ink-3)]">{item.listingTitle || t('Listing removed')}</span>
          <span className={`t-sm mt-0.5 block truncate ${item.unread ? 'text-[var(--ink)]' : 'text-[var(--ink-3)]'}`}>
            {item.lastMessage.mine ? `${t('You')}: ` : ''}
            {item.lastMessage.body}
          </span>
          <span className="mt-2 flex items-center gap-2">
            <Pill tone={pill.tone}>{pill.label}</Pill>
            {item.unread && <span className="h-2 w-2 rounded-full bg-[var(--badge)]" aria-label={t('Unread')} />}
          </span>
        </span>
      </button>
    </li>
  )
}
