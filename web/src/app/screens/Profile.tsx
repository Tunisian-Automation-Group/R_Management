import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { formatEur } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { useBookings, useMeQuery, useMyListings, useSaved } from '../../data/repo.ts'
import { signOut, useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon } from '../components/Icon.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Avatar, Button, Card, Row, Skeleton } from '../components/ui.tsx'

const TAKEN = ['accepted', 'active', 'completed']

export function Profile() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const session = useSession()
  const authReady = useAuthReady()
  const me = useMeQuery()
  const saved = useSaved()
  const listings = useMyListings()
  const asGuest = useBookings('requester')
  const asHost = useBookings('owner')

  if (!authReady || (session && me.isPending)) {
    return (
      <Screen title="You">
        <Skeleton className="h-[136px] rounded-[var(--radius-card)]" />
        <Skeleton className="mt-3 h-[200px] rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!session || !me.data?.owner) {
    return (
      <Screen title="You">
        <SignedOut what="see your profile, saved listings and record" next="/profile" />
      </Screen>
    )
  }

  const you = me.data.owner
  const spent = (asGuest.data?.items ?? [])
    .filter((b) => TAKEN.includes(b.status))
    .reduce((n, b) => n + b.match.quote.total, 0)
  const earned = (asHost.data?.items ?? [])
    .filter((b) => TAKEN.includes(b.status))
    .reduce((n, b) => n + b.match.quote.ownerNet, 0)
  const shortlist = saved.data?.items ?? []

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
            <p className="t-sm truncate text-[var(--ink-3)]">{session.email}</p>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3 border-t border-[var(--line)] pt-5">
          <Stat label="Listed" value={String(listings.data?.items.length ?? 0)} />
          <Stat label="Earned" value={formatEur(earned)} accent />
          <Stat label="Spent" value={formatEur(spent)} />
        </div>
      </Card>

      {/* The shortlist. Hearting something only helps if there is somewhere to
          come back to it. */}
      <section>
        <SectionHead
          title="Saved"
          aside={shortlist.length ? String(shortlist.length) : undefined}
          className="mt-7"
        />
        {shortlist.length === 0 ? (
          <Card className="p-5">
            <p className="t-body text-[var(--ink-3)]">
              Tap the heart on anything you are comparing and it waits for you here.
            </p>
          </Card>
        ) : (
          <ul className="ruled">
            {shortlist.map(({ listing: l, owner: o }) => {
              const id = l.id
              return (
                <li key={id}>
                  <button
                    onClick={() => nav(`/listing/${id}`)}
                    className="flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-70"
                  >
                    <Photo
                      src={l.photos?.[0]}
                      alt={l.title}
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
        <SectionHead title="Account" className="mt-7" />
        <Card className="p-5">
          <p className="t-sm text-[var(--ink-2)]">
            Signed in as <span className="font-semibold text-[var(--ink)]">{session.email}</span> on this
            device. Signing out keeps everything you listed and booked.
          </p>
          <Button className="mt-4" variant="secondary" onClick={() =>
              void signOut().then(() => {
                qc.clear()
                nav('/')
              })
            }>
            Sign out
          </Button>
        </Card>
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
            <Row label="Payment" value="By card, held until the host accepts" />
          </div>
        </Card>
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
            Your sign-in (email and password) is held by Amazon Cognito; card and bank
            details by Stripe. Cappy keeps your name, district, and what you list, book
            and rate. Nothing is sold or shared.
          </p>
        </Card>
      </section>

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
