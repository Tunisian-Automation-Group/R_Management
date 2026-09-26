import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../data/auth.ts'
import {
  acceptOffer,
  extendBooking,
  offerRefund,
  reportLateReturn,
  useAttemptKey,
  useClaims,
  useDispute,
} from '../../data/repo.ts'
import type { Booking } from '../../domain/types.ts'
import { formatMoney, minorPerMajor } from '../../domain/money.ts'
import { durationLabel } from '../../domain/categories.ts'
import { messageOf, useToast } from '../store.tsx'
import { Banner, Button, Card, Chip, Field, Input, Row, Sheet, Textarea } from './ui.tsx'
import { relative } from '../format.ts'
import { useOnline } from './Offline.tsx'
import { t } from '../../i18n.ts'

const toMinor = (text: string, currency: string): number | null => {
  const n = Number(text.replace(/\s/g, '').replace(',', '.'))
  return text.trim() && Number.isFinite(n) && n >= 0 ? Math.round(n * minorPerMajor(currency)) : null
}

/**
 * The two sides settle a dispute themselves (S-21): either offers what goes
 * back to the renter, the other accepts it or counters within 72 hours, after
 * which Cappy's staff decide.
 */
export function DisputeOffers({ booking, asOwner, otherName }: { booking: Booking; asOwner: boolean; otherName: string }) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const me = useSession()?.sub
  const online = useOnline()
  const dispute = useDispute(booking.id, true)
  const [offering, setOffering] = useState(false)
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)
  const attempt = useAttemptKey()
  const d = dispute.data
  if (!d) return null
  const cur = d.currency
  const mine = d.offer?.by === me
  const typed = toMinor(amount, cur)
  const bad = typed === null || typed > d.amount
  const refresh = () =>
    Promise.all(['dispute', 'booking', 'bookings'].map((k) => qc.invalidateQueries({ queryKey: k === 'bookings' ? [k] : [k, booking.id] })))
  const offer = async () => {
    if (typed === null) return
    setBusy(true)
    try {
      await offerRefund(booking.id, typed)
      toast(t('Offer sent. {name} has 72 hours to answer', { name: otherName }))
      setOffering(false)
      setAmount('')
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await refresh()
    }
  }
  const accept = async () => {
    if (!d.offer) return
    setBusy(true)
    const body = { refundAmount: d.offer.refundAmount }
    try {
      await acceptOffer(booking.id, d.offer.refundAmount, attempt.keyFor(body))
      attempt.settle()
      toast(t('Agreed. The dispute is settled'))
    } catch (err) {
      attempt.settle(err)
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await refresh()
    }
  }
  return (
    <Card className="mt-3 p-5">
      <h2 className="t-label mb-2">{t('Settle it between you')}</h2>
      {d.escalatedAt ? (
        <p className="t-sm text-[var(--ink-2)]">{t('You did not agree within 72 hours, so Cappy’s staff decide now. You can still agree on an offer until then.')}</p>
      ) : (
        <p className="t-sm text-[var(--ink-2)]">
          {t('Agree on what goes back to the renter, and it is settled at once. Otherwise Cappy decides {when}.', { when: relative(d.respondBy) })}
        </p>
      )}
      {d.offer && (
        <div className="mt-3 rounded-[var(--radius-control)] bg-[var(--sunken)] p-4">
          <Row
            label={mine ? t('Your offer') : t('{name} offers', { name: otherName })}
            value={t('{amount} back to the renter', { amount: formatMoney(d.offer.refundAmount, cur) })}
            strong
          />
          <p className="t-sm text-[var(--ink-3)]">
            {t('Of {total}. The owner is paid the rest.', { total: formatMoney(d.amount, cur) })} {mine ? t('Waiting for {name}.', { name: otherName }) : ''}
          </p>
          {!mine && (
            <Button className="mt-3" disabled={busy || !online} onClick={() => void accept()}>
              {t('Accept {amount}', { amount: formatMoney(d.offer.refundAmount, cur) })}
            </Button>
          )}
        </div>
      )}
      <Button className="mt-3" variant="secondary" disabled={!online} onClick={() => setOffering(true)}>
        {d.offer ? t('Make another offer') : t('Make an offer')}
      </Button>
      <Sheet
        open={offering}
        onClose={() => setOffering(false)}
        title={t('What should go back to the renter?')}
        footer={
          <Button block size="lg" disabled={busy || bad || !online} onClick={() => void offer()}>
            {typed !== null && !bad ? t('Offer {amount}', { amount: formatMoney(typed, cur) }) : t('Offer')}
          </Button>
        }
      >
        <div className="pb-3">
          <Field
            label={asOwner ? t('You give back') : t('You get back')}
            htmlFor={`${id}-amount`}
            error={amount && bad ? t('Between nothing and {total}.', { total: formatMoney(d.amount, cur) }) : undefined}
            hint={t('Of {total}. The owner is paid the rest.', { total: formatMoney(d.amount, cur) })}
          >
            <Input id={`${id}-amount`} inputMode="decimal" value={amount} invalid={Boolean(amount && bad)} onChange={(e) => setAmount(e.target.value)} />
          </Field>
        </div>
      </Sheet>
    </Card>
  )
}

/** How a report ended, once it did (V5-7): upheld or not, and where the money went. */
export function DisputeDecided({ booking, asOwner }: { booking: Booking; asOwner: boolean }) {
  const dispute = useDispute(booking.id, true)
  if (!dispute.data) return null
  const cur = booking.currency
  const refund = booking.refundAmount ?? 0
  const amount = formatMoney(refund, cur)
  const full = booking.status === 'cancelled'
  const body = asOwner
    ? full
      ? t('The renter gets {amount} back, and this booking is not paid out to you.', { amount })
      : refund
        ? t('The renter gets {amount} back, and you are paid the rest.', { amount })
        : t('It was decided in your favour: your payout is on its way.')
    : full
      ? t('You get {amount} back to your card.', { amount })
      : refund
        ? t('You get {amount} back to your card, and the owner is paid the rest.', { amount })
        : t('It was decided in the owner’s favour, so the owner is paid. If you disagree, get help with this booking.')
  return (
    <div className="mt-3">
      <Banner tone={refund ? 'success' : 'warn'} title={t('The reported problem was decided')} body={body} />
    </div>
  )
}

const EXTEND_HOURS = [1, 2, 4]

/** One more stretch straight after, while the booking is on (S-12). */
export function Extend({ booking }: { booking: Booking }) {
  const nav = useNavigate()
  const toast = useToast()
  const online = useOnline()
  const [open, setOpen] = useState(false)
  const [hours, setHours] = useState(1)
  const [busy, setBusy] = useState(false)
  const attempt = useAttemptKey()
  const on = (booking.status === 'accepted' || booking.status === 'active') && booking.requirement.mode === 'window'
  if (!on || Date.now() >= Date.parse(booking.match.end)) return null
  const extend = async () => {
    setBusy(true)
    const body = { hours }
    try {
      const made = await extendBooking(booking.id, hours, attempt.keyFor(body))
      attempt.settle()
      setOpen(false)
      toast(made.booking.status === 'accepted' ? t('Extended') : t('Asked for more time'))
      nav(`/bookings/${made.booking.id}`)
    } catch (err) {
      attempt.settle(err)
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Card className="mt-3 flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="t-sm text-[var(--ink-3)]">{t('Need it longer? Ask for the time straight after, if it is free.')}</p>
        <Button size="sm" variant="secondary" disabled={!online} onClick={() => setOpen(true)}>
          {t('Extend')}
        </Button>
      </Card>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t('How much longer?')}
        footer={
          <Button block size="lg" disabled={busy || !online} onClick={() => void extend()}>
            {t('Book {duration} more and pay', { duration: durationLabel(hours) })}
          </Button>
        }
      >
        <div className="flex flex-wrap gap-2 pb-3">
          {EXTEND_HOURS.map((h) => (
            <Chip key={h} selected={h === hours} onClick={() => setHours(h)}>
              {durationLabel(h)}
            </Chip>
          ))}
        </div>
        <p className="t-sm pb-3 text-[var(--ink-3)]">
          {booking.listing?.instantBook
            ? t('A new booking right after this one, at the listing’s price, confirmed at once.')
            : t('A new booking right after this one, at the listing’s price. The owner accepts it first.')}
        </p>
      </Sheet>
    </>
  )
}

const DAY = 86_400_000

/** The owner reports a late return within 24 hours after the end (S-12). Staff
 *  confirm it; nothing is charged yet. */
export function LateReturn({ booking, renterName }: { booking: Booking; renterName: string }) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const online = useOnline()
  const end = Date.parse(booking.match.end)
  // The server says from when (lateReturnFrom: the end, earlier locally).
  const from = booking.lateReturnFrom ? Date.parse(booking.lateReturnFrom) : end
  const inWindow = ['active', 'completed', 'disputed'].includes(booking.status) && Date.now() >= from && Date.now() <= end + DAY
  const claims = useClaims(booking.id, ['active', 'completed', 'disputed'].includes(booking.status))
  const [open, setOpen] = useState(false)
  const [minutes, setMinutes] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const mins = Number(minutes)
  const items = claims.data ?? []
  if (!inWindow && items.length === 0) return null
  const send = async () => {
    setBusy(true)
    try {
      await reportLateReturn(booking.id, mins, note.trim())
      toast(t('Reported. Cappy looks at it and tells you both'))
      setOpen(false)
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await qc.invalidateQueries({ queryKey: ['claims', booking.id] })
    }
  }
  return (
    <Card className="mt-3 p-5">
      <h2 className="t-label mb-2">{t('Late return')}</h2>
      {items.map((c) => (
        <p key={c.id} className="t-sm text-[var(--ink-2)]">
          {t('{n} minutes late, {amount}', { n: c.minutesLate, amount: formatMoney(c.amount, c.currency) })} ·{' '}
          {c.status === 'open' ? t('Cappy is looking at it') : c.status === 'confirmed' ? t('Confirmed by Cappy') : t('Not confirmed by Cappy')}
        </p>
      ))}
      {inWindow && items.length === 0 && (
        <>
          <p className="t-sm text-[var(--ink-3)]">{t('Came back late? Report it within 24 hours after the end. The first 30 minutes are free.')}</p>
          <Button className="mt-3" size="sm" variant="secondary" disabled={!online} onClick={() => setOpen(true)}>
            {t('Report a late return')}
          </Button>
        </>
      )}
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t('How late did {name} bring it back?', { name: renterName })}
        footer={
          <Button block size="lg" disabled={busy || !online || !(mins > 0)} onClick={() => void send()}>
            {t('Report the late return')}
          </Button>
        }
      >
        <div className="space-y-4 pb-3">
          <Field label={t('Minutes late')} htmlFor={`${id}-mins`} hint={t('The time after the first 30 minutes is charged at the listing’s rate, plus a capped late fee, once Cappy confirms it.')}>
            <Input id={`${id}-mins`} inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value.replace(/\D/g, '').slice(0, 4))} />
          </Field>
          <Field label={t('What happened (optional)')} htmlFor={`${id}-note`}>
            <Textarea id={`${id}-note`} rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
      </Sheet>
    </Card>
  )
}
