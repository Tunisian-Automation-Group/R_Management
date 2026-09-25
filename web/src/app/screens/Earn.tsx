import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Booking } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { idleHours } from '../../domain/availability.ts'
import { formatEur } from '../../domain/money.ts'
import { useCappy, useLookups, useMe } from '../store.tsx'
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

export function Earn() {
  const nav = useNavigate()
  const { state, send } = useCappy()
  const ME = useMe()
  const { owner, slotsFor, myListings, me } = useLookups()
  const [declining, setDeclining] = useState<Booking | null>(null)
  const [reason, setReason] = useState(DECLINE_REASONS[0])

  const mine = state.ready ? myListings() : []
  const active = mine.filter((l) => l.active)

  const inbound = state.bookings.filter((b) => b.match.ownerId === ME)
  const requests = inbound.filter((b) => b.status === 'requested')
  const confirmed = inbound.filter((b) => ['accepted', 'active', 'completed'].includes(b.status))

  const { hoursIdle, unsold, sold } = useMemo(() => {
    const soldHours = confirmed.reduce((n, b) => n + b.match.quote.hours, 0)
    let total = 0
    let money = 0
    for (const l of active) {
      // Only this week's windows. Nobody acts on "idle last year".
      const week = slotsFor(l.id).filter(
        (s) => Date.parse(s.start) < Date.now() + 7 * 86_400_000,
      )
      const h = idleHours(week)
      total += h
      money += h * l.ratePerHour
    }
    const remaining = Math.max(0, total - soldHours)
    return {
      hoursIdle: remaining,
      unsold: total > 0 ? Math.round((remaining / total) * money) : 0,
      sold: soldHours,
    }
  }, [active, confirmed, slotsFor])

  const earned = confirmed.reduce((n, b) => n + b.match.quote.ownerNet, 0)

  if (!state.ready) {
    return (
      <Screen title="Earn">
        <Skeleton className="h-[16px] w-[46%]" />
        <Skeleton className="mt-4 h-[60px] w-[62%]" />
        <Skeleton className="mt-4 h-[44px] w-full" />
        <Skeleton className="mt-5 h-[210px] w-full rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!state.session) {
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
              const who = b.requesterId ? owner(b.requesterId) : undefined
              const listing = state.world.listings.find((l) => l.id === b.match.listingId)
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
                          wants {listing?.title ?? 'your listing'} ·{' '}
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
                        onClick={() => {
                          send({ type: 'BOOKING_ACCEPTED', id: b.id })
                          send({ type: 'TOAST', message: 'Accepted. They have the details now' })
                        }}
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
            const week = slotsFor(l.id).filter(
              (s) => Date.parse(s.start) < Date.now() + 7 * 86_400_000,
            )
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
                      onClick={() =>
                        send({
                          type: l.active ? 'LISTING_PAUSED' : 'LISTING_RESUMED',
                          id: l.id,
                        })
                      }
                    >
                      {l.active ? 'Pause' : 'Resume'}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        send({ type: 'LISTING_REMOVED', id: l.id })
                        send({ type: 'TOAST', message: `${l.title} removed` })
                      }}
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
      <section>
        <SectionHead title="Your record as a host" className="mt-7" />
        <Card className="p-5">
          <div className="flex items-center gap-3.5">
            <Avatar initials={me().initials} size={44} />
            <div className="min-w-0 flex-1">
              <p className="text-[15.5px] font-semibold">{me().name}</p>
              <p className="t-sm tnum text-[var(--ink-3)]">
                {me().jobsDone} booking{me().jobsDone === 1 ? '' : 's'} ·{' '}
                {Math.round((me().onTimeJobs / Math.max(1, me().jobsDone)) * 100)}% on time
              </p>
            </div>
            <span className="tnum text-[19px] font-bold">
              {(me().ratingSum / Math.max(1, me().jobsDone)).toFixed(1)}★
            </span>
          </div>
        </Card>
      </section>

      <Sheet
        open={Boolean(declining)}
        onClose={() => setDeclining(null)}
        title="Decline this request"
        footer={
          <Button
            block
            size="lg"
            variant="danger"
            onClick={() => {
              if (!declining) return
              send({ type: 'BOOKING_DECLINED', id: declining.id, reason })
              send({ type: 'TOAST', message: 'Declined. They have been told' })
              setDeclining(null)
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
              body="Your listing stays live and the hours are offered to the next person searching."
            />
          </div>
        </div>
      </Sheet>
    </Screen>
  )
}
