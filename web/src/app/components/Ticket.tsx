import { useEffect, useRef } from 'react'
import type { Booking } from '../../domain/types.ts'
import { formatMoney } from '../../domain/money.ts'
import { locale, t } from '../../i18n.ts'
import { responseTime, time } from '../format.ts'
import { Photo } from './Photo.tsx'

const ics = (b: Booking, title: string) => {
  const z = (iso: string) => new Date(iso).toISOString().replace(/[-:]|\.\d{3}/g, '')
  return `data:text/calendar;charset=utf-8,${encodeURIComponent(
    ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Cappy//EN', 'BEGIN:VEVENT', `UID:${b.id}@cappy`, `DTSTAMP:${z(b.createdAt)}`,
      `DTSTART:${z(b.match.start)}`, `DTEND:${z(b.match.end)}`, `SUMMARY:${title.replace(/[,;\\]/g, '\\$&')}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n'),
  )}`
}

/**
 * The booking-confirmed moment (VD-15, visual direction §2.8): the hour you
 * were given, as a ticket on the plate, once, right after sending. A native
 * modal dialog, so focus, Escape and the inert page come with it.
 */
export function Ticket({
  booking,
  title,
  instant,
  ownerName,
  responseMins,
  onMessage,
  onDone,
}: {
  booking: Booking
  title: string
  /** Booked at once (paid), rather than asked for. */
  instant: boolean
  ownerName: string
  responseMins?: number | null
  onMessage: () => void
  onDone: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (d && !d.open) d.showModal()
  }, [])
  const reply = responseTime(responseMins)
  return (
    <dialog
      ref={ref}
      aria-labelledby="ticket-title"
      onClose={onDone}
      className="ticket-scrim fixed inset-0 m-0 h-full max-h-none w-full max-w-none overflow-y-auto bg-[var(--field)] p-0 text-[var(--on-field)]"
    >
      <div className="flex min-h-full flex-col items-center justify-center gap-6 px-4 py-[calc(var(--safe-top)+24px)]">
        <div className="ticket plate-lit w-full max-w-sm overflow-hidden rounded-[var(--radius-plate)] shadow-[var(--shadow-plate)]">
          <div className="p-5">
            <div className="flex items-center gap-3">
              {booking.listing?.photo && (
                <Photo alt="" src={booking.listing.photo} categoryId={booking.requirement.category} aspect={1} className="h-11 w-11 shrink-0 rounded-full" />
              )}
              <p className="t-body min-w-0 font-semibold">{title}</p>
            </div>
            <p id="ticket-title" className="t-h1 mt-4">
              {new Date(booking.match.start).toLocaleDateString(locale(), { weekday: 'long' })}
            </p>
            <p className="t-figure t-ticket-time mt-1 text-[var(--sky)]">
              {time(booking.match.start)}–{time(booking.match.end)}
            </p>
            <p className="t-sm mt-2 text-[var(--on-field-dim)]">
              {new Date(booking.match.start).toLocaleDateString(locale(), { day: 'numeric', month: 'long' })}
              {booking.listing?.district ? ` · ${booking.listing.district}` : ''} · {t('with {name}', { name: ownerName })}
            </p>
          </div>
          {/* The perforation between the ticket and its stub. */}
          <div className="ticket-perf" aria-hidden="true" />
          <p className="t-sm px-5 py-3 font-semibold">
            {instant ? (
              <span>{t('Booked')} · {formatMoney(booking.match.quote.total, booking.currency)}</span>
            ) : (
              <span className="text-[var(--sky)]">{t('Waiting for {name}', { name: ownerName })}</span>
            )}
          </p>
        </div>
        <p className="t-lede ticket-step max-w-sm text-center">
          {instant ? t('All set. {name} knows you are coming.', { name: ownerName }) : t('Request sent to {name}', { name: ownerName })}
          {!instant && reply ? `. ${reply}` : ''}
        </p>
        <div className="flex w-full max-w-sm flex-wrap justify-center gap-2">
          <button type="button" onClick={onMessage} className="ticket-step glass glass-dark min-h-11 rounded-[var(--radius-capsule)] px-5 text-label font-semibold">
            {t('Message {name}', { name: ownerName })}
          </button>
          <a
            href={ics(booking, title)}
            download="cappy-booking.ics"
            className="ticket-step glass glass-dark inline-flex min-h-11 items-center rounded-[var(--radius-capsule)] px-5 text-label font-semibold"
          >
            {t('Add to calendar')}
          </a>
          <button
            type="button"
            autoFocus
            onClick={() => ref.current?.close()}
            className="ticket-step min-h-11 w-full rounded-[var(--radius-capsule)] px-5 text-label font-semibold underline"
          >
            {t('Open the booking')}
          </button>
        </div>
      </div>
    </dialog>
  )
}
