import { useEffect, useState } from 'react'
import { useNav } from '../nav.ts'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { formatMoney } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS, moved } from '../../domain/pricing.ts'
import {
  ApiError,
  deleteMe,
  exportMyData,
  saveProfile,
  unblockPerson,
  useBlocks,
  useBookings,
  useDistricts,
  useMarkets,
  useNoticeSettings,
  saveNoticeSettings,
  type NoticeCategory,
  useMeQuery,
  useMyListings,
  useOwner,
  useSaved,
} from '../../data/repo.ts'
import type { Owner } from '../../domain/types.ts'
import { messageOf, useToast } from '../store.tsx'
import { BusinessFields, businessErrors, cleanBusiness, emptyBusiness, serverBusinessErrors, type BusinessErrors } from '../components/BusinessFields.tsx'
import { CountrySelect } from '../components/CountrySelect.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { accessToken, deleteAccount, endSession, signOut, useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { AppearanceSwitch, GlassSwitch, LanguageSwitch, Screen, SectionHead, ThemeToggle } from '../components/AppShell.tsx'
import { Icon } from '../components/Icon.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Avatar, Button, Card, Field, Input, Row, Segmented, Sheet, Skeleton } from '../components/ui.tsx'
import { t } from '../../i18n.ts'
import { day, percent } from '../format.ts'
import { canOpenSettings, enablePush, isNative, openAppSettings, pushPermission, type PushPermission } from '../../native.ts'


export function Profile() {
  const nav = useNav()
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
      <Screen title={t('You')} action={<ThemeToggle className="grid md:hidden" />}>
        <Skeleton className="h-[136px] rounded-[var(--radius-card)]" />
        <Skeleton className="mt-3 h-[200px] rounded-[var(--radius-card)]" />
      </Screen>
    )
  }

  if (!session || !me.data?.owner) {
    return (
      <Screen title={t('You')} action={<ThemeToggle className="grid md:hidden" />}>
        <SignedOut what={t('see your profile, saved listings and record')} next="/profile" />
      </Screen>
    )
  }

  const you = me.data.owner
  // What really moved, after refunds and no-shows: the server's reckoning (V8-2).
  const spent = (asGuest.data?.items ?? []).reduce((n, b) => {
    const m = moved(b)
    return n + m.charged - m.refunded
  }, 0)
  // Paid out means done: completed, or a renter no-show that paid the owner.
  const earned = (asHost.data?.items ?? [])
    .filter((b) => b.status === 'completed' || b.status === 'cancelled')
    .reduce((n, b) => n + moved(b).ownerNet, 0)
  // ponytail: one currency per person, their market's (ADR 0013); sums never mix currencies until then.
  const currency = asHost.data?.items[0]?.currency ?? asGuest.data?.items[0]?.currency
  const shortlist = saved.data?.items ?? []

  return (
    <Screen title={t('You')} action={<ThemeToggle className="grid md:hidden" />}>
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
          <Stat label={t('Earned')} value={formatMoney(earned, currency)} accent />
          <Stat label={t('Spent')} value={formatMoney(spent, currency)} />
        </div>
      </Card>

      {/* Preferences first (UX-48): how the app looks and speaks, before the
          record and the essays. */}
      <section>
        <SectionHead title={t('Preferences')} className="mt-7" />
        <Card className="space-y-5 p-5">
          <div>
            <p className="t-label mb-2">{t('Appearance')}</p>
            <AppearanceSwitch />
            <p className="t-sm mt-3 text-[var(--ink-3)]">{t('Light is the default. System follows your phone or computer. Saved on this device only.')}</p>
          </div>
          <div>
            <p className="t-label mb-2">{t('Glass effects')}</p>
            <GlassSwitch />
            <p className="t-sm mt-3 text-[var(--ink-3)]">{t('Reduced turns the frosted glass off, for older phones or if you prefer plain surfaces.')}</p>
          </div>
          <div>
            <p className="t-label mb-2">{t('Language')}</p>
            <LanguageSwitch />
          </div>
        </Card>
      </section>


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
                  <div className="relative flex w-full items-center gap-4 py-3.5 text-left transition-opacity duration-[var(--dur-short)] hover:opacity-70">
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
                        className="block w-full truncate text-left text-body font-semibold after:absolute after:inset-0 after:content-['']"
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
            <span className="font-semibold break-all text-[var(--ink)]">{session.email}</span>
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
          <SignOutEverywhere />
        </Card>
      </section>

      <NotificationSettings />

      <Blocked />

      {session?.staff && (
        <section>
          <SectionHead title={t('Staff')} className="mt-7" />
          <Card className="p-5">
            <Link to="/admin" className="text-body font-semibold underline underline-offset-4">
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
                  .catch((err) => toast(messageOf(err), 'error'))
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
            <Row label={t('Service fee')} value={t('{pct} of the booking', { pct: percent(PLATFORM_FEE_BPS / 10_000) })} />
            <Row label={t('Paid by')} value={t('Taken from the total, not added on top')} />
            <Row label={t('Payment')} value={t('By card, held until the host accepts')} />
          </div>
        </Card>
      </section>

      <section>
        <SectionHead title={t('Help')} className="mt-7" />
        <Card className="p-5">
          <nav aria-label={t('Help')} className="flex flex-col gap-3 text-body font-semibold">
            <Link to="/help">{t('Help and answers')}</Link>
            <Link to="/help/safety">{t('How we keep you safe')}</Link>
          </nav>
        </Card>
      </section>

      <section>
        <SectionHead title={t('Legal')} className="mt-7" />
        <Card className="p-5">
          <nav aria-label={t('Legal')} className="flex flex-col gap-3 text-body font-semibold">
            <Link to="/legal/impressum">Impressum</Link>
            <Link to="/legal/privacy">{t('Privacy Policy')}</Link>
            <Link to="/legal/terms">{t('Terms of Use')}</Link>
            <Link to="/legal/withdrawal">{t('Right of withdrawal')}</Link>
            <Link to="/legal/ranking">{t('How ranking works')}</Link>
            <Link to="/legal/report">{t('Reporting content')}</Link>
            <Link to="/legal/accessibility">{t('Accessibility')}</Link>
          </nav>
        </Card>
      </section>

      <button
        onClick={() => nav('/earn/new')}
        className="mt-5 flex w-full items-center justify-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] py-3.5 text-body font-semibold text-[var(--accent-text)]
          transition-colors duration-[var(--dur-short)] hover:border-[var(--accent)]"
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
  const [business, setBusiness] = useState(you.business ?? emptyBusiness)
  const [bizErrors, setBizErrors] = useState<BusinessErrors>({})
  const { live } = useMarkets()
  const [country, setCountry] = useState(you.country ?? 'DE')
  // A country's own districts only (M-2).
  const inCountry = Object.fromEntries(Object.entries(districts.data ?? {}).filter(([, d]) => d.country === country))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    // Every problem at once, each under its field (V4-20).
    const biz = kind === 'business' ? businessErrors(business) : {}
    setBizErrors(biz)
    const nameBad = name.trim().length < 2
    setError(nameBad ? t('Tell people what to call you.') : null)
    if (nameBad || Object.keys(biz).length) return
    const where = inCountry[district] ? district : Object.keys(inCountry).sort()[0] ?? district
    setBusy(true)
    try {
      await saveProfile({ name: name.trim(), kind, district: where, country, ...(kind === 'business' ? { business: cleanBusiness(business) } : {}) })
      await qc.invalidateQueries({ queryKey: ['me'] })
      toast(t('Profile saved'))
      onClose()
    } catch (err) {
      // Each field the server refused goes under that field (V4-20).
      const onForm = err instanceof ApiError ? serverBusinessErrors(err.fields) : {}
      if (Object.keys(onForm).length) setBizErrors(onForm)
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
          <Input id="p-name" autoComplete="name" value={name} invalid={Boolean(error)} onChange={(e) => setName(e.target.value)} />
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
        {kind === 'business' && <BusinessFields id="p-biz" value={business} onChange={setBusiness} errors={bizErrors} />}
        <Field label={t('Country')} htmlFor="p-country" hint={t('Your listings are priced in its currency.')}>
          <CountrySelect
            id="p-country"
            // A country no longer live stays selectable for the person already in it.
            countries={live.includes(country) ? live : [...live, country]}
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          />
        </Field>
        <Field label={t('Where are you?')} htmlFor="p-where">
          <DistrictSelect
            id="p-where"
            districts={inCountry}
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
          />
        </Field>
      </div>
    </Sheet>
  )
}

function DeleteAccount({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNav()
  const qc = useQueryClient()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const remove = async () => {
    setBusy(true)
    setError(null)
    try {
      await deleteMe() // 409 while a booking or payout is still open (U-9)
      // The platform has forgotten the person: from here they are signed out
      // whatever happens (FL-11), never sent back to onboarding. The server
      // deletes the sign-in too (P-23); this is the quick path, tried twice.
      for (let i = 0; i < 2; i++) {
        try {
          await deleteAccount()
          break
        } catch {
          // Already gone server-side, or offline: the server finishes it.
        }
      }
      endSession()
      qc.clear()
      toast(t('Your account is deleted'))
      nav('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          err.until
            ? t('{reason} You can delete your account from {date}.', { reason: err.message, date: day(err.until) })
            : err.message,
        )
      } else setError(messageOf(err))
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
      <div className="space-y-3 pb-3 text-body leading-[1.4375rem] text-[var(--ink-2)]">
        <p>{t('This cannot be undone.')}</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>{t('Your sign-in, profile and saved listings are deleted.')}</li>
          <li>{t('Your listings are taken down, and your name is removed from reviews you wrote.')}</li>
          {/* True since D-1: the photos go too (FL-12). */}
          <li>{t('Your photos are deleted, including the hand-over photos you took.')}</li>
          <li>{t('Past bookings, payments and invoices are kept without your name for up to ten years, because tax law requires records of them.')}</li>
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
      <p className={`tnum mt-1.5 text-title-s font-bold ${accent ? 'text-[var(--money)]' : ''}`}>
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
                  toast(messageOf(err), 'error')
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
      <span className="truncate text-body font-semibold">{person.data?.name ?? t('Someone')}</span>
      <Button variant="secondary" size="sm" onClick={onUnblock}>
        {t('Unblock')}
      </Button>
    </li>
  )
}

/** Every device this account is signed in on, at once (U-35): a lost phone. */
function SignOutEverywhere() {
  const qc = useQueryClient()
  const nav = useNav()
  const toast = useToast()
  const [asking, setAsking] = useState(false)
  return (
    <>
      <Button className="ml-2 mt-4" variant="quiet" onClick={() => setAsking(true)}>
        {t('Sign out everywhere')}
      </Button>
      <Sheet
        open={asking}
        onClose={() => setAsking(false)}
        title={t('Sign out on every device?')}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              onClick={() =>
                void signOut({ everywhere: true }).then(
                  () => {
                    qc.clear()
                    toast(t('Signed out on every device'))
                    nav('/login', { replace: true })
                  },
                  (err: unknown) => toast(messageOf(err), 'error'),
                )
              }
            >
              {t('Sign out everywhere')}
            </Button>
            <Button block variant="quiet" onClick={() => setAsking(false)}>
              {t('Cancel')}
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {t('Every phone, tablet and browser signed in to your account is signed out at once and stops getting notifications. Use it if a device is lost or someone else knows your password.')}
        </p>
      </Sheet>
    </>
  )
}

/** Notifications: the bell's list, and on a phone whether push is on (U-36). */
function NotificationSettings() {
  const [perm, setPerm] = useState<PushPermission>('unavailable')
  useEffect(() => {
    void pushPermission().then(setPerm)
    // Coming back from Settings: look again.
    const again = () => document.visibilityState === 'visible' && void pushPermission().then(setPerm)
    document.addEventListener('visibilitychange', again)
    return () => document.removeEventListener('visibilitychange', again)
  }, [])
  return (
    <section>
      <SectionHead title={t('Notifications')} className="mt-7" />
      <Card className="p-5">
        <Link to="/notifications" className="text-body font-semibold underline underline-offset-4">
          {t('See all notifications')}
        </Link>
        {isNative && perm === 'denied' && (
          <div className="mt-4 border-t border-[var(--line)] pt-4">
            <p className="text-body font-semibold">{t('Notifications are off')}</p>
            <p className="t-sm mt-1 text-[var(--ink-3)]">
              {canOpenSettings
                ? t('You will not hear about new requests or answers until you are back in the app. Emails still arrive.')
                : t('Turn them on in Settings → Apps → Cappy → Notifications. Emails still arrive.')}
            </p>
            {canOpenSettings && (
              <Button className="mt-3" variant="secondary" onClick={openAppSettings}>
                {t('Turn on in Settings')}
              </Button>
            )}
          </div>
        )}
        {isNative && perm === 'prompt' && (
          <div className="mt-4 border-t border-[var(--line)] pt-4">
            <Button
              variant="secondary"
              onClick={() => void enablePush(accessToken, true).then(setPerm)}
            >
              {t('Turn on notifications')}
            </Button>
          </div>
        )}
        <Channels />
      </Card>
    </section>
  )
}

const CATEGORY_LABEL: Record<NoticeCategory, string> = {
  bookings: 'Bookings and requests',
  messages: 'Messages',
  payouts: 'Payouts',
  marketing: 'News and offers',
}

/** Push and email, per kind of notification (V3-21). Marketing stays off until chosen. */
function Channels() {
  const qc = useQueryClient()
  const toast = useToast()
  const session = useSession()
  const q = useNoticeSettings()
  if (!q.data) {
    return (
      <p className="t-sm mt-4 text-[var(--ink-3)]">
        {t('Only bookings and messages; never marketing. Booking changes always arrive by email; messages by email too, at most one every 15 minutes per conversation.')}
      </p>
    )
  }
  const settings = q.data
  const flip = (c: NoticeCategory, ch: 'push' | 'email') => {
    const next = { categories: { ...settings.categories, [c]: { ...settings.categories[c], [ch]: !settings.categories[c][ch] } } }
    const key = ['noticeSettings', session?.sub]
    qc.setQueryData(key, next)
    saveNoticeSettings(next).catch((err: unknown) => {
      qc.setQueryData(key, settings)
      toast(messageOf(err), 'error')
    })
  }
  return (
    <>
    {/* Rows that wrap, not a table with fixed columns: at 200 % text in
        French a table ran 409 px wide on a 390 px phone (V7-8). */}
    <ul className="mt-4 border-t border-[var(--line)]">
      {(Object.keys(CATEGORY_LABEL) as NoticeCategory[]).map((c) => (
        <li key={c} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-[var(--line)] py-3">
          <span className="min-w-0 text-body">{t(CATEGORY_LABEL[c])}</span>
          <span className="flex gap-4">
            {(['push', 'email'] as const).map((ch) => (
              <label key={ch} className="t-sm flex items-center gap-1.5 text-[var(--ink-3)]">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-[var(--ink)]"
                  aria-label={`${t(CATEGORY_LABEL[c])}: ${ch === 'push' ? t('Push') : t('Email')}`}
                  checked={settings.categories[c]?.[ch] ?? false}
                  onChange={() => flip(c, ch)}
                />
                {ch === 'push' ? t('Push') : t('Email')}
              </label>
            ))}
          </span>
        </li>
      ))}
    </ul>
    <p className="t-sm mt-2 text-[var(--ink-3)]">
      {t('Booking confirmations and changes always arrive by email, whatever you choose here.')}
    </p>
    </>
  )
}
