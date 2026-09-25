import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { formatEur } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import {
  deleteMe,
  exportMyData,
  saveProfile,
  unblockPerson,
  useBlocks,
  useBookings,
  useDistricts,
  useMeQuery,
  useMyListings,
  useOwner,
  useSaved,
} from '../../data/repo.ts'
import type { Owner } from '../../domain/types.ts'
import { messageOf, useToast } from '../store.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { deleteAccount, signOut, useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { LanguageSwitch, Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon } from '../components/Icon.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Avatar, Button, Card, Field, Input, Row, Segmented, Sheet, Skeleton } from '../components/ui.tsx'
import { locale, t } from '../../i18n.ts'

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
      <Screen title={t('You')}>
        <Skeleton className="h-[136px] rounded-[var(--radius-card)]" />
        <Skeleton className="mt-3 h-[200px] rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!session || !me.data?.owner) {
    return (
      <Screen title={t('You')}>
        <SignedOut what={t('see your profile, saved listings and record')} next="/profile" />
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
    <Screen title={t('You')}>
      <Card className="p-5">
        <div className="flex items-center gap-4">
          <Avatar initials={you.initials} size={56} />
          <div className="min-w-0">
            <p className="t-h3 truncate">{you.name}</p>
            <p className="t-sm tnum text-[var(--ink-3)]">
              {you.district} · {t('member since {year}', { year: you.joinedYear })}
            </p>
            <p className="t-sm truncate text-[var(--ink-3)]">{session.email}</p>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3 border-t border-[var(--line)] pt-5">
          <Stat label={t('Listed')} value={String(listings.data?.items.length ?? 0)} />
          <Stat label={t('Earned')} value={formatEur(earned)} accent />
          <Stat label={t('Spent')} value={formatEur(spent)} />
        </div>
      </Card>

      {/* The shortlist. Hearting something only helps if there is somewhere to
          come back to it. */}
      <section>
        <SectionHead
          title={t('Saved')}
          aside={shortlist.length ? String(shortlist.length) : undefined}
          className="mt-7"
        />
        {shortlist.length === 0 ? (
          <Card className="p-5">
            <p className="t-body text-[var(--ink-3)]">
              {t('Tap the heart on anything you are comparing and it waits for you here.')}
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
          title={t('Account')}
          aside={
            <button className="font-semibold text-[var(--accent-text)]" onClick={() => setEditing(true)}>
              {t('Edit profile')}
            </button>
          }
          className="mt-7"
        />
        <Card className="p-5">
          <p className="t-sm text-[var(--ink-2)]">
            {t('Signed in as')}{' '}
            <span className="font-semibold text-[var(--ink)]">{session.email}</span>
            {' '}{t('on this device. Signing out keeps everything you listed and booked.')}
          </p>
          <Button className="mt-4" variant="secondary" onClick={() =>
              void signOut().then(() => {
                qc.clear()
                toast(t('Signed out'))
                nav('/')
              })
            }>
            {t('Sign out')}
          </Button>
        </Card>
      </section>

      <Blocked />

      {session?.staff && (
        <section>
          <SectionHead title={t('Staff')} className="mt-7" />
          <Card className="p-5">
            <Link to="/admin" className="text-[14.5px] font-semibold underline underline-offset-4">
              {t('Open the staff console')}
            </Link>
          </Card>
        </section>
      )}

      <section>
        <SectionHead title={t('Your data')} className="mt-7" />
        <Card className="p-5">
          <p className="t-sm text-[var(--ink-2)]">
            {t('Download everything Cappy holds about you, or delete your account.')}
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
              {t('Download my data')}
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)}>
              {t('Delete account')}
            </Button>
          </div>
        </Card>
      </section>

      <section>
        <SectionHead title={t('How Cappy works')} className="mt-7" />
        <Card className="p-5">
          <p className="t-body text-[var(--ink-2)]">
            {t('Capacity is idle most of the time. Cappy sells those hours: a printer free overnight, a PA rig between gigs, a mill with a gap between contracts. You buy the outcome, not the machine, and one engine matches every job to whoever can actually run it.')}
          </p>
          <div className="mt-4 border-t border-[var(--line)] pt-4">
            <Row label={t('Cappy fee')} value={t('{pct} % of the booking', { pct: (PLATFORM_FEE_BPS / 100).toLocaleString(locale()) })} />
            <Row label={t('Paid by')} value={t('Taken from the total, not added on top')} />
            <Row label={t('Payment')} value={t('By card, held until the host accepts')} />
          </div>
        </Card>
      </section>

      <section>
        <SectionHead title={t('Language')} className="mt-7" />
        <Card className="p-5">
          <LanguageSwitch />
        </Card>
      </section>

      <section>
        <SectionHead title={t('Legal')} className="mt-7" />
        <Card className="p-5">
          <nav aria-label={t('Legal')} className="flex flex-col gap-3 text-[14.5px] font-semibold">
            <Link to="/legal/impressum">Impressum</Link>
            <Link to="/legal/privacy">{t('Privacy Policy')}</Link>
            <Link to="/legal/terms">{t('Terms of Use')}</Link>
            <Link to="/legal/withdrawal">{t('Right of withdrawal')}</Link>
            <Link to="/legal/ranking">{t('How ranking works')}</Link>
            <Link to="/legal/report">{t('Reporting content')}</Link>
          </nav>
        </Card>
      </section>

      <button
        onClick={() => nav('/earn/new')}
        className="mt-5 flex w-full items-center justify-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] py-3.5 text-[14px] font-semibold text-[var(--accent-text)]
          transition-colors duration-[160ms] hover:border-[var(--accent)]"
      >
        <Icon name="plus" size={17} strokeWidth={2.2} />
        {t('List something you own')}
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
    if (name.trim().length < 2) return setError(t('Tell people what to call you.'))
    setBusy(true)
    setError(null)
    try {
      await saveProfile({ name: name.trim(), kind, district })
      await qc.invalidateQueries({ queryKey: ['me'] })
      toast(t('Profile saved'))
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
      title={t('Edit profile')}
      footer={
        <Button block size="lg" disabled={busy} onClick={() => void save()}>
          {busy ? t('Saving…') : t('Save')}
        </Button>
      }
    >
      <div className="space-y-5 pb-3">
        <Field label={t('Your name')} htmlFor="p-name" error={error ?? undefined}>
          <Input id="p-name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t('You are')}>
          <Segmented<'person' | 'business'>
            label={t('Person or business')}
            value={kind}
            onChange={setKind}
            options={[
              { value: 'person', label: t('A person') },
              { value: 'business', label: t('A business') },
            ]}
          />
        </Field>
        <Field label={t('Where are you?')} htmlFor="p-where">
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
      toast(t('Your account is deleted'))
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
      title={t('Delete your account?')}
      footer={
        <div className="space-y-2">
          <Button block size="lg" variant="danger" disabled={busy} onClick={() => void remove()}>
            {busy ? t('Deleting…') : t('Delete my account')}
          </Button>
          <Button block variant="quiet" onClick={onClose}>
            {t('Keep it')}
          </Button>
        </div>
      }
    >
      <div className="space-y-3 pb-3 text-[15px] leading-[23px] text-[var(--ink-2)]">
        <p>{t('This cannot be undone.')}</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>{t('Your sign-in, profile, saved listings and photos are deleted.')}</li>
          <li>{t('Your listings are taken down, and your name is removed from reviews you wrote.')}</li>
          <li>{t('Past bookings and payments are kept, without your name, because the law requires records of them.')}</li>
        </ul>
        <p>{t('Bookings still open (requested, confirmed or in progress) have to finish or be cancelled first.')}</p>
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

/** People the person blocked, with a way back. */
function Blocked() {
  const blocks = useBlocks()
  const qc = useQueryClient()
  const toast = useToast()
  const ids = blocks.data ?? []
  if (ids.length === 0) return null
  return (
    <section>
      <SectionHead title={t('Blocked people')} className="mt-7" />
      <Card className="p-5">
        <p className="t-sm mb-3 text-[var(--ink-3)]">
          {t('They cannot message you or book with you, and you cannot with them.')}
        </p>
        <ul className="space-y-2">
          {ids.map((sub) => (
            <BlockedRow
              key={sub}
              sub={sub}
              onUnblock={async () => {
                try {
                  await unblockPerson(sub)
                  toast(t('Unblocked'))
                } catch (err) {
                  toast(messageOf(err))
                } finally {
                  await qc.invalidateQueries({ queryKey: ['blocks'] })
                }
              }}
            />
          ))}
        </ul>
      </Card>
    </section>
  )
}

function BlockedRow({ sub, onUnblock }: { sub: string; onUnblock: () => void }) {
  const person = useOwner(sub)
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="truncate text-[15px] font-semibold">{person.data?.name ?? t('Someone')}</span>
      <Button variant="secondary" size="sm" onClick={onUnblock}>
        {t('Unblock')}
      </Button>
    </li>
  )
}
