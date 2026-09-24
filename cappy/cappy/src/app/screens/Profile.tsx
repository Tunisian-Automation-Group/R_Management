import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { formatEur } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { ME, useCappy, useLookups } from '../store.tsx'
import * as repo from '../../data/repo.ts'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon } from '../components/Icon.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Avatar, Banner, Button, Card, Row, Sheet, Skeleton } from '../components/ui.tsx'

export function Profile() {
  const nav = useNavigate()
  const { state } = useCappy()
  const { me, myListings, listing, owner, slotsFor } = useLookups()
  const [resetting, setResetting] = useState(false)

  if (!state.ready) {
    return (
      <Screen title="You">
        <Skeleton className="h-[136px] rounded-[var(--radius-card)]" />
        <Skeleton className="mt-3 h-[200px] rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  const you = me()
  const asGuest = state.bookings.filter((b) => b.match.ownerId !== ME)
  const asHost = state.bookings.filter((b) => b.match.ownerId === ME)
  const spent = asGuest
    .filter((b) => ['accepted', 'active', 'completed'].includes(b.status))
    .reduce((n, b) => n + b.match.quote.total, 0)
  const earned = asHost
    .filter((b) => ['accepted', 'active', 'completed'].includes(b.status))
    .reduce((n, b) => n + b.match.quote.ownerNet, 0)

  return (
    <Screen title="You">
      <Card className="p-5">
        <div className="flex items-center gap-4">
          <Avatar initials={you.initials} size={56} />
          <div className="min-w-0">
            <p className="t-h3 truncate">{you.name}</p>
            <p className="t-sm tnum text-[var(--ink-3)]">
              {you.district} · member since {you.joinedYear}
            </p>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3 border-t border-[var(--line)] pt-5">
          <Stat label="Listed" value={String(myListings().length)} />
          <Stat label="Earned" value={formatEur(earned)} accent />
          <Stat label="Spent" value={formatEur(spent)} />
        </div>
      </Card>

      {/* The shortlist. Hearting something only helps if there is somewhere to
          come back to it. */}
      <section>
        <SectionHead
          title="Saved"
          aside={state.saved.length ? String(state.saved.length) : undefined}
          className="mt-7"
        />
        {state.saved.length === 0 ? (
          <Card className="p-5">
            <p className="t-body text-[var(--ink-3)]">
              Tap the heart on anything you are comparing and it waits for you here.
            </p>
          </Card>
        ) : (
          <ul className="ruled">
            {state.saved.map((id) => {
              const l = listing(id)
              if (!l) return null
              const o = owner(l.ownerId)
              return (
                <li key={id}>
                  <button
                    onClick={() => nav(`/listing/${id}`)}
                    className="flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-70"
                  >
                    <Photo
                      src={l.photos?.[0]}
                      alt={l.title}
                      slots={slotsFor(id)}
                      categoryId={l.category}
                      aspect={1}
                      className="w-[56px] shrink-0 rounded-[var(--radius-plate)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-semibold">{l.title}</span>
                      <span className="t-sm block truncate text-[var(--ink-3)]">
                        {o?.name}, {l.district}
                      </span>
                    </span>
                    <SaveButton id={id} title={l.title} className="relative shrink-0" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section>
        <SectionHead title="How Cappy works" className="mt-7" />
        <Card className="p-5">
          <p className="t-body text-[var(--ink-2)]">
            Capacity is idle most of the time. Cappy sells those hours: a printer free
            overnight, a PA rig between gigs, a mill with a gap between contracts. You
            buy the outcome, not the machine, and one engine matches every job to
            whoever can actually run it.
          </p>
          <div className="mt-4 border-t border-[var(--line)] pt-4">
            <Row label="Cappy fee" value={`${PLATFORM_FEE_BPS / 100}% of the booking`} />
            <Row label="Paid by" value="Taken from the total, not added on top" />
            <Row label="Settlement" value="Directly between you and the host" />
          </div>
        </Card>
      </section>

      <section>
        <SectionHead title="This build" className="mt-7" />
        <Banner
          tone="warn"
          title="This build is a prototype"
          body="Hosts, machines and availability here are realistic examples, not real people or real businesses. Requests you send are auto-accepted after a few seconds so you can see the whole flow. Nothing is charged and no money moves."
        />
      </section>

      <section>
        <SectionHead title="Legal" className="mt-7" />
        <Card className="p-5">
          {/* §5 DDG. Required on a publicly reachable German service, fill these
              in before sharing the link outside the team. */}
          <h3 className="t-label mb-2.5">Impressum</h3>
          <p className="t-sm leading-[20px] text-[var(--ink-3)]">
            Angaben gemäß § 5 DDG
            <br />
            <span className="text-[var(--warn)]">[ Name ]</span>
            <br />
            <span className="text-[var(--warn)]">[ Straße und Hausnummer ]</span>
            <br />
            <span className="text-[var(--warn)]">[ PLZ, Ort ]</span>
            <br />
            E-Mail: <span className="text-[var(--warn)]">[ E-Mail-Adresse ]</span>
          </p>

          <h3 className="t-label mb-2.5 mt-5 border-t border-[var(--line)] pt-5 text-[var(--ink-4)]">
            Privacy
          </h3>
          <p className="t-sm leading-[20px] text-[var(--ink-3)]">
            Everything you do stays in this browser. There is no account to make and
            nothing is sent to a server. Clearing the data below erases all of it.
          </p>
        </Card>
      </section>

      <section className="mt-8">
        <Button block variant="danger" onClick={() => setResetting(true)}>
          Reset all data
        </Button>
      </section>

      <Sheet
        open={resetting}
        onClose={() => setResetting(false)}
        title="Reset everything?"
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              onClick={async () => {
                await repo.reset()
                location.href = '/'
              }}
            >
              Delete and start over
            </Button>
            <Button block variant="quiet" onClick={() => setResetting(false)}>
              Keep my data
            </Button>
          </div>
        }
      >
        <p className="t-body pb-4 text-[var(--ink-2)]">
          Your bookings, your listings and every rating you have given will be deleted and the app
          goes back to how it started. This cannot be undone.
        </p>
      </Sheet>

      <button
        onClick={() => nav('/earn/new')}
        className="mt-5 flex w-full items-center justify-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] py-3.5 text-[14px] font-semibold text-[var(--accent-text)]
          transition-colors duration-[160ms] hover:border-[var(--accent)]"
      >
        <Icon name="plus" size={17} strokeWidth={2.2} />
        List something you own
      </button>
    </Screen>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <p className="t-label">{label}</p>
      <p className={`tnum mt-1.5 text-[19px] font-bold ${accent ? 'text-[var(--accent-text)]' : ''}`}>
        {value}
      </p>
    </div>
  )
}
