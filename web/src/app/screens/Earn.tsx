import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import type { Booking, Owner, Slot } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { idleHours } from '../../domain/availability.ts'
import { formatEur } from '../../domain/money.ts'
import * as repo from '../../data/repo.ts'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { messageOf, useToast } from '../store.tsx'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { CapacityBar } from '../components/CapacityBar.tsx'
import { Photo } from '../components/Photo.tsx'
import { Icon } from '../components/Icon.tsx'
import { Avatar, Banner, Button, Card, Chip, EmptyState, Pill, Sheet, Skeleton } from '../components/ui.tsx'
import { ago, range } from '../format.ts'

const DECLINE_REASONS = [
  'Already promised it to someone',
  'Turns out I need it then',
  'It needs a repair first',
  'Too short notice for me',
]

const WEEK = 7 * 86_400_000
const thisWeek = (slots: Slot[]) => slots.filter((s) => Date.parse(s.start) < Date.now() + WEEK)

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

  const mine = listingsQ.data?.items.map((v) => v.listing) ?? []
  const active = mine.filter((l) => l.active)
  // Each listing's windows, for the idle-hours figures. ponytail: one request per
  // listing; a /me/slots endpoint if owners start listing dozens of things.
  const details = useQueries({
    queries: mine.map((l) => ({ queryKey: ['listing', l.id], queryFn: () => repo.getListing(l.id) })),
  })
  const slotsById = new Map(details.flatMap((d) => (d.data ? [[d.data.listing.id, d.data.slots] as const] : [])))
  const slotsFor = (id: string): Slot[] => slotsById.get(id) ?? []

  const inbound = inboundQ.data?.items ?? []
  const requests = inbound.filter((b) => b.status === 'requested')
  const confirmed = inbound.filter((b) => ['accepted', 'active', 'completed'].includes(b.status))
  // Who is asking: their public profile, for the name and initials.
  const askers = useQueries({
    queries: requests.map((b) => ({
      queryKey: ['owner', b.requesterId],
      queryFn: () => repo.getOwner(b.requesterId!),
      enabled: Boolean(b.requesterId),
    })),
  })
  const askerOf = (b: Booking): Owner | undefined => askers.find((q) => q.data?.id === b.requesterId)?.data

  const soldHours = confirmed.reduce((n, b) => n + b.match.quote.hours, 0)
  let total = 0
  let money = 0
  for (const l of active) {
    // Only this week's windows. Nobody acts on "idle last year".
    const h = idleHours(thisWeek(slotsFor(l.id)))
    total += h
    money += h * l.ratePerHour
  }
  const hoursIdle = Math.max(0, total - soldHours)
  const unsold = total > 0 ? Math.round((hoursIdle / total) * money) : 0
  const sold = soldHours
  const earned = confirmed.reduce((n, b) => n + b.match.quote.ownerNet, 0)

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
      <Screen title="Earn">
        <Skeleton className="h-[16px] w-[46%]" />
        <Skeleton className="mt-4 h-[60px] w-[62%]" />
        <Skeleton className="mt-4 h-[44px] w-full" />
        <Skeleton className="mt-5 h-[210px] w-full rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!session) {
    return (
      <Screen title="Earn" sub="Everything you own has hours you never use.">
        <SignedOut what="list something and answer requests" next="/earn" />
      </Screen>
    )
  }

  if (mine.length === 0) {
    return (
      <Screen
        title="Earn"
        sub="Everything you own has hours you never use."
      >
        <EmptyState
          icon="wallet"
          title="Nothing listed yet"
          body="A printer running overnight, a PA rig between gigs, a treated room, a saw in the cupboard. If it is idle, somebody nearby needs it for an hour."
          action={
            <Button size="lg" icon="plus" onClick={() => nav('/earn/new')}>
              List your first thing
            </Button>
          }
        />
      </Screen>
    )
  }

  return (
    <Screen
      title="Earn"
      action={
        <Button size="sm" variant="secondary" icon="plus" onClick={() => nav('/earn/new')}>
          Add
        </Button>
      }
    >
      {connect.data && !connect.data.payoutsEnabled && (
        <div className="mb-6">
          <Banner
            tone="warn"
            title={
              params.get('payments') === 'done' ? 'Stripe is checking your details' : 'Set up payouts to take bookings'
            }
            body="Buyers can only book you once Stripe knows where to send your money. It takes a few minutes, and Cappy never sees your bank details."
            action={
              <Button size="sm" disabled={busy} onClick={() => void payouts()}>
                {connect.data.connected ? 'Continue setup' : 'Set up payouts'}
              </Button>
            }
          />
        </div>
      )}

      {/* ------------------------------------------- the number that matters */}
      <section className="-mt-1">
        <p className="t-label">Still idle this week</p>
        <p className="mt-3 flex flex-wrap items-baseline gap-x-2.5">
          <span className="t-display tnum">{Math.round(hoursIdle)}</span>
          <span className="text-[20px] font-medium text-[var(--ink-4)]">hours</span>
        </p>
        <p className="t-lede mt-3 text-[var(--ink-2)]">
          <span className="hl font-semibold">{formatEur(unsold)}</span> of time nobody is paying
          you for.
        </p>
        {sold > 0 && (
          <p className="t-sm tnum mt-2.5 font-semibold text-[var(--success-text)]">
            {Math.round(sold)} h sold · {formatEur(earned)} earned
          </p>
        )}
      </section>

      <Card className="mt-6 p-5">
        <CapacityBar
          slots={active.flatMap((l) => slotsFor(l.id))}
          booked={confirmed[0]?.match ?? null}
          intent="earn"
          showLegend
        />
      </Card>

      {/* --------------------------------------------------------- requests */}
      <section>
        <SectionHead
          title={
            <span className="flex items-center gap-2.5">
              Requests
              {requests.length > 0 && <Pill tone="accent">{requests.length} waiting</Pill>}
            </span>
          }
          className="mt-7"
        />

        {requests.length === 0 ? (
          <Card className="p-5">
            <p className="t-body text-[var(--ink-3)]">
              No one is waiting on you. Requests land here and the window is held until you
              answer.
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
                          {who?.name ?? 'Someone nearby'}
                        </p>
                        <p className="t-sm text-[var(--ink-3)]">
                          wants {b.listing?.title ?? 'your listing'} ·{' '}
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
                        asked {ago(b.createdAt)} · fits a gap you are not using
                      </p>
                    </div>

                    {/* Sized to the label. A full-width Accept is a phone habit; on
                        a page it became a 1,500px red bar that read as an alarm. */}
                    <div className="mt-4 flex gap-2">
                      <Button
                        className="flex-1 md:flex-none md:px-7"
                        disabled={busy}
                        onClick={() =>
                          void write(() => repo.actOnBooking(b.id, 'accept'), 'Accepted. They have the details now')
                        }
                      >
                        Accept
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setReason(DECLINE_REASONS[0])
                          setDeclining(b)
                        }}
                      >
                        Decline
                      </Button>
                    </div>
                  </Card>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* --------------------------------------------------------- listings */}
      <section>
        <SectionHead title="Your listings" aside={`${mine.length}`} className="mt-7" />
        <ul className="space-y-3">
          {mine.map((l) => {
            const week = thisWeek(slotsFor(l.id))
            const h = idleHours(week)
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
                      className={`w-[56px] shrink-0 rounded-[var(--radius-plate)] ${l.active ? '' : 'opacity-40'}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15.5px] font-semibold">{l.title}</p>
                      <p className="t-sm tnum text-[var(--ink-3)]">
                        {formatEur(l.ratePerHour)}/h ·{' '}
                        {l.active ? `${Math.round(h)} h free this week` : 'Paused'}
                      </p>
                    </div>
                    {!l.active && <Pill tone="warn">Paused</Pill>}
                  </div>

                  {l.active && week.length > 0 && (
                    <div className="mt-4">
                      <CapacityBar slots={week} size="sm" intent="earn" />
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--line)] pt-4">
                    <Button size="sm" variant="secondary" onClick={() => nav(`/listing/${l.id}`)}>
                      View as a guest
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={l.active ? 'pause' : 'check'}
                      disabled={busy}
                      onClick={() =>
                        void write(
                          () => (l.active ? repo.pauseListing(l.id) : repo.resumeListing(l.id)),
                          l.active ? `${l.title} paused` : `${l.title} is live again`,
                        )
                      }
                    >
                      {l.active ? 'Pause' : 'Resume'}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={busy}
                      onClick={() => void write(() => repo.removeListing(l.id), `${l.title} removed`)}
                    >
                      Remove
                    </Button>
                  </div>
                </Card>
              </li>
            )
          })}
        </ul>
      </section>

      {/* ----------------------------------------------------- your record */}
      {you && (
        <section>
          <SectionHead title="Your record as a host" className="mt-7" />
          <Card className="p-5">
            <div className="flex items-center gap-3.5">
              <Avatar initials={you.initials} size={44} />
              <div className="min-w-0 flex-1">
                <p className="text-[15.5px] font-semibold">{you.name}</p>
                <p className="t-sm tnum text-[var(--ink-3)]">
                  {you.jobsDone} booking{you.jobsDone === 1 ? '' : 's'} ·{' '}
                  {Math.round((you.onTimeJobs / Math.max(1, you.jobsDone)) * 100)}% on time
                </p>
              </div>
              <span className="tnum text-[19px] font-bold">
                {you.jobsDone ? `${(you.ratingSum / you.jobsDone).toFixed(1)}★` : 'New'}
              </span>
            </div>
          </Card>
        </section>
      )}

      <Sheet
        open={Boolean(declining)}
        onClose={() => setDeclining(null)}
        title="Decline this request"
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
              void write(() => repo.declineBooking(id, reason), 'Declined. They have been told')
            }}
          >
            Send decline
          </Button>
        }
      >
        <div className="pb-3">
          <p className="t-body mb-5 text-[var(--ink-3)]">
            A reason takes two seconds and keeps people booking with you again.
          </p>
          <div className="flex flex-wrap gap-2">
            {DECLINE_REASONS.map((r) => (
              <Chip key={r} selected={reason === r} onClick={() => setReason(r)}>
                {r}
              </Chip>
            ))}
          </div>
          <div className="mt-6">
            <Banner
              tone="warn"
              title="The window goes back on the market"
              body="Your listing stays live and the hours are offered to the next person searching. Their card hold is released."
            />
          </div>
        </div>
      </Sheet>
    </Screen>
  )
}
