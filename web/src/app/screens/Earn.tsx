import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import type { Booking, Listing, Owner, Slot } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { idleHours } from '../../domain/availability.ts'
import { formatEur, formatEurExact } from '../../domain/money.ts'
import * as repo from '../../data/repo.ts'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { messageOf, useToast } from '../store.tsx'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { CapacityBar } from '../components/CapacityBar.tsx'
import { Photo } from '../components/Photo.tsx'
import { Icon } from '../components/Icon.tsx'
import { Avatar, Banner, Button, Card, Chip, EmptyState, oneDecimal, Pill, Sheet, Skeleton } from '../components/ui.tsx'
import { ago, range, renterRecord } from '../format.ts'
import { locale, plural, t } from '../../i18n.ts'

export const DECLINE_REASONS = [
  'Already promised it to someone',
  'Turns out I need it then',
  'It needs a repair first',
  'Too short notice for me',
]

const DAY = 86_400_000
/** Today and the six days after it: the same seven columns the week chart draws. */
const weekEnd = () => new Date().setHours(0, 0, 0, 0) + 7 * DAY
const thisWeek = (slots: Slot[]) => slots.filter((s) => Date.parse(s.start) < weekEnd())
const HELD = ['accepted', 'active']

export function Earn() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const toast = useToast()
  const session = useSession()
  const authReady = useAuthReady()
  const me = repo.useMeQuery()
  const listingsQ = repo.useMyListings()
  const inboundQ = repo.useBookings('owner')
  const connect = repo.useConnectStatus()
  const [declining, setDeclining] = useState<Booking | null>(null)
  const [reason, setReason] = useState(DECLINE_REASONS[0])
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<Listing | null>(null)

  const mine = listingsQ.data?.items.map((v) => v.listing) ?? []
  const held = new Set((listingsQ.data?.items ?? []).filter((v) => v.held).map((v) => v.listing.id))
  const invoices = repo.useInvoices()
  const active = mine.filter((l) => l.active)
  // Each listing's upcoming windows come with it, for the idle-hours figures.
  const slotsById = new Map((listingsQ.data?.items ?? []).map((v) => [v.listing.id, v.slots ?? []] as const))
  const slotsFor = (id: string): Slot[] => slotsById.get(id) ?? []

  const inbound = inboundQ.data?.items ?? []
  const byStart = (a: Booking, b: Booking) => Date.parse(a.match.start) - Date.parse(b.match.start)
  const requests = inbound.filter((b) => b.status === 'requested').sort(byStart)
  // Sold this week: what the chart draws and what comes off the idle hours.
  const soldThisWeek = inbound.filter(
    (b) => [...HELD, 'completed'].includes(b.status) && Date.parse(b.match.start) < weekEnd() && Date.parse(b.match.end) > Date.now(),
  )
  const comingUp = inbound.filter((b) => HELD.includes(b.status)).sort(byStart)
  const soldFor = (listingId: string) =>
    soldThisWeek.filter((b) => b.match.listingId === listingId).reduce((n, b) => n + b.match.quote.hours, 0)
  // Who is asking: their public profile, for the name and initials.
  const askers = useQueries({
    queries: requests.map((b) => ({
      queryKey: ['owner', b.requesterId],
      queryFn: () => repo.getOwner(b.requesterId!),
      enabled: Boolean(b.requesterId),
    })),
  })
  const askerOf = (b: Booking): Owner | undefined => askers.find((q) => q.data?.id === b.requesterId)?.data

  // Only this week's windows, less what is already sold. Nobody acts on "idle last year".
  const freeFor = (id: string) => Math.max(0, idleHours(thisWeek(slotsFor(id))) - soldFor(id))
  let hoursIdle = 0
  let unsold = 0
  for (const l of active) {
    const h = freeFor(l.id)
    hoursIdle += h
    unsold += h * l.ratePerHour
  }
  const sold = soldThisWeek.reduce((n, b) => n + b.match.quote.hours, 0)
  // Earned means paid out: completed. Accepted and active are still to come.
  const earned = inbound.filter((b) => b.status === 'completed').reduce((n, b) => n + b.match.quote.ownerNet, 0)
  const upcoming = comingUp.reduce((n, b) => n + b.match.quote.ownerNet, 0)

  const write = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await fn()
      toast(message)
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
      await Promise.all(
        [['bookings'], ['myListings'], ['listing']].map((queryKey) => qc.invalidateQueries({ queryKey })),
      )
    }
  }

  const payouts = async () => {
    setBusy(true)
    try {
      // Stripe's own onboarding page; it sends them back to /earn.
      location.href = (await repo.startPayouts()).url
    } catch (err) {
      toast(messageOf(err))
      setBusy(false)
    }
  }

  const you = me.data?.owner

  if (!authReady || (session && (listingsQ.isPending || inboundQ.isPending))) {
    return (
      <Screen title={t('Earn')}>
        <Skeleton className="h-[16px] w-[46%]" />
        <Skeleton className="mt-4 h-[60px] w-[62%]" />
        <Skeleton className="mt-4 h-[44px] w-full" />
        <Skeleton className="mt-5 h-[210px] w-full rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!session) {
    return (
      <Screen title={t('Earn')} sub={t('Everything you own has hours you never use.')}>
        <SignedOut what={t('list something and answer requests')} next="/earn" />
      </Screen>
    )
  }

  if (mine.length === 0) {
    return (
      <Screen
        title={t('Earn')}
        sub={t('Everything you own has hours you never use.')}
      >
        <EmptyState
          icon="wallet"
          title={t('Nothing listed yet')}
          body={t('A printer running overnight, a PA rig between gigs, a treated room, a saw in the cupboard. If it is idle, somebody nearby needs it for an hour.')}
          action={
            <Button size="lg" icon="plus" to={'/earn/new'}>
              {t('List your first thing')}
            </Button>
          }
        />
      </Screen>
    )
  }

  return (
    <Screen
      title={t('Earn')}
      action={
        <Button size="sm" variant="secondary" icon="plus" to={'/earn/new'}>
          {t('Add')}
        </Button>
      }
    >
      {connect.data && !connect.data.payoutsEnabled && (
        <div className="mb-6">
          <Banner
            tone="warn"
            title={
              params.get('payments') === 'done' ? t('Stripe is checking your details') : t('Set up payouts to take bookings')
            }
            body={t('Buyers can only book you once Stripe knows where to send your money. It takes a few minutes, and Cappy never sees your bank details.')}
            action={
              <Button size="sm" disabled={busy} onClick={() => void payouts()}>
                {connect.data.connected ? t('Continue setup') : t('Set up payouts')}
              </Button>
            }
          />
        </div>
      )}

      {/* ------------------------------------------- the number that matters */}
      <section className="-mt-1">
        <p className="t-label">{t('Still idle this week')}</p>
        <p className="mt-3 flex flex-wrap items-baseline gap-x-2.5">
          <span className="t-display tnum">{Math.round(hoursIdle)}</span>
          <span className="text-[20px] font-medium text-[var(--ink-4)]">{t('hours')}</span>
        </p>
        <p className="t-lede mt-3 text-[var(--ink-2)]">
          <span className="hl font-semibold">{formatEur(unsold)}</span> {t('of time nobody is paying you for.')}
        </p>
        {(sold > 0 || earned > 0) && (
          <p className="t-sm tnum mt-2.5 font-semibold text-[var(--success-text)]">
            {t('{h} h sold this week · {earned} earned', { h: Math.round(sold), earned: formatEur(earned) })}
            {upcoming > 0 && ` · ${t('{amount} to come', { amount: formatEur(upcoming) })}`}
          </p>
        )}
      </section>

      <Card className="mt-6 p-5">
        <CapacityBar
          slots={active.flatMap((l) => slotsFor(l.id))}
          booked={soldThisWeek.map((b) => b.match)}
          intent="earn"
          showLegend
        />
      </Card>

      {/* --------------------------------------------------------- requests */}
      <section>
        <SectionHead
          title={
            <span className="flex items-center gap-2.5">
              {t('Requests')}
              {requests.length > 0 && <Pill tone="accent">{t('{n} waiting', { n: requests.length })}</Pill>}
            </span>
          }
          className="mt-7"
        />

        {requests.length === 0 ? (
          <Card className="p-5">
            <p className="t-body text-[var(--ink-3)]">
              {t('No one is waiting on you. Requests land here and the window is held until you answer.')}
            </p>
          </Card>
        ) : (
          <ul className="space-y-3">
            {requests.map((b) => {
              const who = askerOf(b)
              return (
                <li key={b.id}>
                  <Card className="anim-rise p-5">
                    <div className="flex items-start gap-3.5">
                      <Avatar initials={who?.initials ?? '??'} size={42} />
                      <div className="min-w-0 flex-1">
                        <p className="text-[15.5px] font-semibold">
                          {who?.name ?? t('Someone nearby')}
                        </p>
                        {who && (
                          <p className="t-sm text-[var(--ink-3)]">{renterRecord(who.renterRatingSum, who.renterJobs)}</p>
                        )}
                        <p className="t-sm text-[var(--ink-3)]">
                          {t('wants {what}', { what: b.listing?.title ?? t('your listing') })} ·{' '}
                          {durationLabel(b.match.quote.hours)}
                        </p>
                      </div>
                      <span className="tnum shrink-0 text-[17px] font-bold text-[var(--accent-text)]">
                        {formatEur(b.match.quote.ownerNet)}
                      </span>
                    </div>

                    <div className="mt-4 rounded-[var(--radius-field)] bg-[var(--sunken)] px-4 py-3">
                      <p className="t-sm tnum flex items-center gap-1.5 font-semibold text-[var(--ink)]">
                        <Icon name="clock" size={14} className="text-[var(--accent-text)]" strokeWidth={2.2} />
                        {range(b.match.start, b.match.end)}
                      </p>
                      <p className="t-sm mt-1 text-[var(--ink-4)]">
                        {t('asked {ago} · fits a gap you are not using', { ago: ago(b.createdAt) })}
                      </p>
                    </div>

                    {/* Sized to the label. A full-width Accept is a phone habit; on
                        a page it became a 1,500px red bar that read as an alarm. */}
                    <div className="mt-4 flex gap-2">
                      <Button
                        className="flex-1 md:flex-none md:px-7"
                        disabled={busy}
                        onClick={() =>
                          void write(() => repo.actOnBooking(b.id, 'accept'), t('Accepted. They have the details now'))
                        }
                      >
                        {t('Accept')}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setReason(DECLINE_REASONS[0])
                          setDeclining(b)
                        }}
                      >
                        {t('Decline')}
                      </Button>
                    </div>
                  </Card>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* ------------------------------------------------------ coming up */}
      {comingUp.length > 0 && (
        <section>
          <SectionHead title={t('Coming up')} aside={`${comingUp.length}`} className="mt-7" />
          <ul className="ruled border-t border-[var(--line)]">
            {comingUp.map((b) => (
              <li key={b.id}>
                <button
                  onClick={() => nav(`/bookings/${b.id}`)}
                  className="flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-70"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold">{b.listing?.title ?? t('Your listing')}</span>
                    <span className="t-sm tnum block truncate text-[var(--ink-3)]">{range(b.match.start, b.match.end)}</span>
                  </span>
                  <Pill tone="success">{b.status === 'active' ? t('In progress') : t('Confirmed')}</Pill>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* --------------------------------------------------------- listings */}
      <section>
        <SectionHead title={t('Your listings')} aside={`${mine.length}`} className="mt-7" />
        <ul className="space-y-3">
          {mine.map((l) => {
            const week = thisWeek(slotsFor(l.id))
            const h = freeFor(l.id)
            return (
              <li key={l.id}>
                <Card className="p-5">
                  <div className="flex items-start gap-3.5">
                    <Photo
                      src={l.photos?.[0]}
                      alt={l.title}
                      slots={week}
                      categoryId={l.category}
                      aspect={1}
                      thumb
                      className={`w-[56px] shrink-0 rounded-[var(--radius-plate)] ${l.active ? '' : 'opacity-40'}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15.5px] font-semibold">{l.title}</p>
                      <p className="t-sm tnum text-[var(--ink-3)]">
                        {formatEur(l.ratePerHour)}/h ·{' '}
                        {l.active ? t('{h} h free this week', { h: Math.round(h) }) : t('Paused')}
                      </p>
                    </div>
                    {held.has(l.id) ? (
                      <Pill tone="warn">{t('Waiting for a quick check')}</Pill>
                    ) : (
                      !l.active && <Pill tone="warn">{t('Paused')}</Pill>
                    )}
                  </div>

                  {l.active && week.length > 0 && (
                    <div className="mt-4">
                      <CapacityBar slots={week} size="sm" intent="earn" />
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--line)] pt-4">
                    <Button size="sm" variant="secondary" to={`/listing/${l.id}`}>
                      {t('View as a guest')}
                    </Button>
                    <Button size="sm" variant="secondary" to={`/earn/edit/${l.id}`}>
                      {t('Edit')}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={l.active ? 'pause' : 'check'}
                      disabled={busy}
                      onClick={() =>
                        void write(
                          () => (l.active ? repo.pauseListing(l.id) : repo.resumeListing(l.id)),
                          l.active ? t('{title} paused', { title: l.title }) : t('{title} is live again', { title: l.title }),
                        )
                      }
                    >
                      {l.active ? t('Pause') : t('Resume')}
                    </Button>
                    {/* Last, and behind a confirmation: removing is not undoable. */}
                    <Button size="sm" variant="danger" disabled={busy} className="ml-auto" onClick={() => setRemoving(l)}>
                      {t('Remove')}
                    </Button>
                  </div>
                </Card>
              </li>
            )
          })}
        </ul>
      </section>

      {/* -------------------------------------------------------- invoices */}
      {(invoices.data?.length ?? 0) > 0 && (
        <section>
          <SectionHead title={t('Invoices')} aside={`${invoices.data!.length}`} className="mt-7" />
          <ul className="ruled border-t border-[var(--line)]">
            {invoices.data!.map((inv) => (
              <li key={inv.number}>
                <button
                  onClick={() => void repo.openInvoice(inv.number).catch((err) => toast(messageOf(err)))}
                  className="flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-70"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold">{inv.number}</span>
                    <span className="t-sm block text-[var(--ink-3)]">
                      {new Date(inv.issuedAt).toLocaleDateString(locale())}
                    </span>
                  </span>
                  <span className="tnum shrink-0 text-[15px] font-semibold">{formatEurExact(inv.gross)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ----------------------------------------------------- your record */}
      {you && (
        <section>
          <SectionHead title={t('Your record as a host')} className="mt-7" />
          <Card className="p-5">
            <div className="flex items-center gap-3.5">
              <Avatar initials={you.initials} size={44} />
              <div className="min-w-0 flex-1">
                <p className="text-[15.5px] font-semibold">{you.name}</p>
                <p className="t-sm tnum text-[var(--ink-3)]">
                  {plural(you.jobsDone, '{n} booking', '{n} bookings')} ·{' '}
                  {t('{pct} % on time', { pct: Math.round((you.onTimeJobs / Math.max(1, you.jobsDone)) * 100) })}
                </p>
              </div>
              <span className="tnum text-[19px] font-bold">
                {you.jobsDone ? `${oneDecimal(you.ratingSum / you.jobsDone)}★` : t('New')}
              </span>
            </div>
          </Card>
        </section>
      )}

      <Sheet
        open={Boolean(removing)}
        onClose={() => setRemoving(null)}
        title={t('Remove {title}?', { title: removing?.title ?? t('this listing') })}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              disabled={busy}
              onClick={() => {
                if (!removing) return
                const l = removing
                setRemoving(null)
                void write(() => repo.removeListing(l.id), t('{title} removed', { title: l.title }))
              }}
            >
              {t('Remove it')}
            </Button>
            <Button block variant="quiet" onClick={() => setRemoving(null)}>
              {t('Keep it')}
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {t('It comes off the market for good. To take a break instead, pause it: you can resume any time. Bookings already confirmed are not affected.')}
        </p>
      </Sheet>

      <Sheet
        open={Boolean(declining)}
        onClose={() => setDeclining(null)}
        title={t('Decline this request')}
        footer={
          <Button
            block
            size="lg"
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (!declining) return
              const id = declining.id
              setDeclining(null)
              void write(() => repo.declineBooking(id, reason), t('Declined. They have been told'))
            }}
          >
            {t('Send decline')}
          </Button>
        }
      >
        <div className="pb-3">
          <p className="t-body mb-5 text-[var(--ink-3)]">
            {t('A reason takes two seconds and keeps people booking with you again.')}
          </p>
          <div className="flex flex-wrap gap-2">
            {DECLINE_REASONS.map((r) => (
              <Chip key={r} selected={reason === r} onClick={() => setReason(r)}>
                {t(r)}
              </Chip>
            ))}
          </div>
          <div className="mt-6">
            {declining && mine.some((l) => l.id === declining.match.listingId && l.active) ? (
              <Banner
                tone="warn"
                title={t('The window goes back on the market')}
                body={t('Your listing stays live and the hours are offered to the next person searching. Their card hold is released.')}
              />
            ) : (
              <Banner
                tone="warn"
                title={t('Their card hold is released')}
                body={t('This listing is paused or removed, so the hours are not offered to anyone else.')}
              />
            )}
          </div>
        </div>
      </Sheet>
    </Screen>
  )
}
