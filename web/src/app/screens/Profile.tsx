import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { formatEur } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import {
  deleteMe,
  exportMyData,
  saveProfile,
  useBookings,
  useDistricts,
  useMeQuery,
  useMyListings,
  useSaved,
} from '../../data/repo.ts'
import type { Owner } from '../../domain/types.ts'
import { messageOf, useToast } from '../store.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { deleteAccount, signOut, useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon } from '../components/Icon.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Avatar, Button, Card, Field, Input, Row, Segmented, Sheet, Skeleton } from '../components/ui.tsx'

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
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)

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
  // Paid out means completed; accepted and active bookings are still to come.
  const earned = (asHost.data?.items ?? [])
    .filter((b) => b.status === 'completed')
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
                  <div className="relative flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-70">
                    <Photo
                      src={l.photos?.[0]}
                      alt={l.title}
                      categoryId={l.category}
                      aspect={1}
                      thumb
                      className="w-[56px] shrink-0 rounded-[var(--radius-plate)]"
                    />
                    <span className="min-w-0 flex-1">
                      <button
                        onClick={() => nav(`/listing/${id}`)}
                        className="block w-full truncate text-left text-[15px] font-semibold after:absolute after:inset-0 after:content-['']"
                      >
                        {l.title}
                      </button>
                      <span className="t-sm block truncate text-[var(--ink-3)]">
                        {o?.name}, {l.district}
                      </span>
                    </span>
                    <SaveButton id={id} title={l.title} className="relative shrink-0" />
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section>
        <SectionHead
          title="Account"
          aside={
            <button className="font-semibold text-[var(--accent-text)]" onClick={() => setEditing(true)}>
              Edit profile
            </button>
          }
          className="mt-7"
        />
        <Card className="p-5">
          <p className="t-sm text-[var(--ink-2)]">
            Signed in as <span className="font-semibold text-[var(--ink)]">{session.email}</span> on this
            device. Signing out keeps everything you listed and booked.
          </p>
          <Button className="mt-4" variant="secondary" onClick={() =>
              void signOut().then(() => {
                qc.clear()
                toast('Signed out')
                nav('/')
              })
            }>
            Sign out
          </Button>
        </Card>
      </section>

      <section>
        <SectionHead title="Your data" className="mt-7" />
        <Card className="p-5">
          <p className="t-sm text-[var(--ink-2)]">
            Download everything Cappy holds about you, or delete your account.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setBusy(true)
                exportMyData()
                  .catch((err) => toast(messageOf(err)))
                  .finally(() => setBusy(false))
              }}
            >
              Download my data
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)}>
              Delete account
            </Button>
          </div>
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
          <nav aria-label="Legal" className="flex flex-col gap-3 text-[14.5px] font-semibold">
            <Link to="/legal/impressum">Impressum</Link>
            <Link to="/legal/privacy">Privacy Policy</Link>
            <Link to="/legal/terms">Terms of Use</Link>
          </nav>
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
      <EditProfile key={String(editing)} open={editing} onClose={() => setEditing(false)} you={you} />
      <DeleteAccount open={deleting} onClose={() => setDeleting(false)} />
    </Screen>
  )
}

function EditProfile({ open, onClose, you }: { open: boolean; onClose: () => void; you: Owner }) {
  const qc = useQueryClient()
  const toast = useToast()
  const districts = useDistricts()
  const [name, setName] = useState(you.name)
  const [kind, setKind] = useState<'person' | 'business'>(you.kind)
  const [district, setDistrict] = useState(you.district)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    if (name.trim().length < 2) return setError('Tell people what to call you.')
    setBusy(true)
    setError(null)
    try {
      await saveProfile({ name: name.trim(), kind, district })
      await qc.invalidateQueries({ queryKey: ['me'] })
      toast('Profile saved')
      onClose()
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Edit profile"
      footer={
        <Button block size="lg" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save'}
        </Button>
      }
    >
      <div className="space-y-5 pb-3">
        <Field label="Your name" htmlFor="p-name" error={error ?? undefined}>
          <Input id="p-name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="You are">
          <Segmented<'person' | 'business'>
            label="Person or business"
            value={kind}
            onChange={setKind}
            options={[
              { value: 'person', label: 'A person' },
              { value: 'business', label: 'A business' },
            ]}
          />
        </Field>
        <Field label="Where are you?" htmlFor="p-where">
          <DistrictSelect
            id="p-where"
            districts={districts.data ?? {}}
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
          />
        </Field>
      </div>
    </Sheet>
  )
}

function DeleteAccount({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const remove = async () => {
    setBusy(true)
    setError(null)
    try {
      await deleteMe() // 409 while a booking is still open: the message says so
      await deleteAccount()
      qc.clear()
      toast('Your account is deleted')
      nav('/', { replace: true })
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Delete your account?"
      footer={
        <div className="space-y-2">
          <Button block size="lg" variant="danger" disabled={busy} onClick={() => void remove()}>
            {busy ? 'Deleting…' : 'Delete my account'}
          </Button>
          <Button block variant="quiet" onClick={onClose}>
            Keep it
          </Button>
        </div>
      }
    >
      <div className="space-y-3 pb-3 text-[15px] leading-[23px] text-[var(--ink-2)]">
        <p>This cannot be undone.</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Your sign-in, profile, saved listings and photos are deleted.</li>
          <li>Your listings are taken down, and your name is removed from reviews you wrote.</li>
          <li>Past bookings and payments are kept, without your name, because the law requires records of them.</li>
        </ul>
        <p>Bookings still open (requested, confirmed or in progress) have to finish or be cancelled first.</p>
        {error && (
          <p role="alert" className="font-semibold text-[var(--danger)]">
            {error}
          </p>
        )}
      </div>
    </Sheet>
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
