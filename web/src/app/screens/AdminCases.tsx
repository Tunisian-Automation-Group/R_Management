import { useId, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Listing } from './Listing.tsx'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../data/auth.ts'
import {
  REASON_CODES,
  approveResolution,
  decideClaim,
  getAudit,
  getCase,
  getCases,
  getPendingResolutions,
  rejectResolution,
  resolveDispute,
  withdrawResolution,
  approveListing,
  getAdminListing,
  useAttemptKey,
  useOwner,
  type AuditEntry,
  type CaseFilters,
  type CaseRow,
  type CaseView,
  type Claim,
  type ReasonCode,
  type Resolution,
  type ResolveOutcome,
} from '../../data/repo.ts'
import { formatMoney, minorPerMajor } from '../../domain/money.ts'
import { messageOf, useToast } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Banner, Button, Card, Check, Field, Input, Row, Segmented, Select, Sheet, Textarea } from '../components/ui.tsx'
import { ago, range, when } from '../format.ts'
import { plural, t } from '../../i18n.ts'

const STATUS_LABEL: Record<string, string> = {
  awaiting_payment: 'Waiting for payment',
  requested: 'Requested',
  accepted: 'Confirmed',
  active: 'In progress',
  completed: 'Finished',
  declined: 'Declined',
  cancelled: 'Cancelled',
  expired: 'Lapsed',
  payment_failed: 'Payment failed',
  disputed: 'Disputed',
}
const statusLabel = (s: string) => t(STATUS_LABEL[s] ?? s)
const OUTCOME_LABEL: Record<ResolveOutcome, string> = {
  refund_buyer: 'Refund the renter in full',
  partial: 'Refund part of it',
  pay_owner: 'Pay the owner',
}
const RESOLUTION_STATUS: Record<Resolution['status'], string> = {
  done: 'Done',
  pending_approval: 'Waiting for a second staff member',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn by the proposer',
}
const PAYMENT_STATUS: Record<string, string> = {
  created: 'Waiting for the card',
  authorised: 'Card held',
  captured: 'Charged',
  refunded: 'Refunded',
  partially_refunded: 'Partly refunded',
  // payments' own vocabulary (payments/tables.py PaymentRow)
  transferred: 'Paid out',
  cancelled: 'Hold released',
  failed: 'Failed',
}
const reasonLabel = (c?: string) => t(REASON_CODES.find(([k]) => k === c)?.[1] ?? c ?? '')

/** A person by name where the profile is readable, else the start of their id. */
export function Person({ id }: { id?: string }) {
  const p = useOwner(id)
  if (!id) return null
  // While it loads, a skeleton word, never an id (V9-12); an unreadable profile says so.
  if (p.isPending) return <span className="skeleton inline-block h-[1em] w-20 rounded-[var(--radius-xs)] align-middle" aria-label={t('Loading')} />
  return <>{p.data?.name ?? t('Former member')}</>
}
// Colleagues by role, never by id prefix (V9-12); the audit log names them when it can.
const staff = (id: string, me?: string) => (id === me ? t('you') : t('another staff member'))

const REFRESH = ['adminResolutions', 'adminCases', 'adminCase', 'audit']

/** "Withdraw my proposal": only on the proposer's own pending one, so a case never
 *  stalls when nobody else is on shift. The case can be decided again after. */
function WithdrawButton({ r }: { r: Resolution }) {
  const qc = useQueryClient()
  const toast = useToast()
  const me = useSession()?.sub
  const [busy, setBusy] = useState(false)
  if (r.status !== 'pending_approval' || r.by !== me) return null
  const go = async () => {
    setBusy(true)
    try {
      await withdrawResolution(r.id)
      toast(t('Withdrawn. You can decide the case again'))
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await Promise.all(REFRESH.map((k) => qc.invalidateQueries({ queryKey: [k] })))
    }
  }
  return (
    <Button size="sm" variant="secondary" disabled={busy} onClick={() => void go()}>
      {t('Withdraw my proposal')}
    </Button>
  )
}

/** Who moved a booking: a party by role, staff by label, Cappy's own jobs as Cappy. */
function actorLabel(e: CaseView['timeline'][number], c: CaseView, me?: string): string {
  if (e.actorKind === 'system') return t('Cappy (automatic)')
  if (e.by === c.requesterId) return t('renter')
  if (e.by === c.ownerId) return t('owner')
  if (e.actorKind === 'staff') return staff(e.by, me)
  return e.actorKind === 'person' ? t('someone') : t('Cappy (automatic)')
}

/** "12,00 €" typed as text → minor units; null when it is not a number. */
function toMinor(text: string, currency: string): number | null {
  const n = Number(text.replace(/\s/g, '').replace(',', '.'))
  return Number.isFinite(n) && n >= 0 ? Math.round(n * minorPerMajor(currency)) : null
}

// --------------------------------------------------------------------- the list

/** Disputed and claimed bookings, and lookup by booking or member (H-9). */
export function Cases() {
  const id = useId()
  const [f, setF] = useState<CaseFilters>({ status: 'disputed' })
  const [draft, setDraft] = useState({ member: '', booking: '' })
  const [cursor, setCursor] = useState<string | undefined>()
  const page = useQuery({ queryKey: ['adminCases', f, cursor], queryFn: () => getCases(f, cursor) })
  const items = page.data?.items ?? []
  const set = (next: CaseFilters) => {
    setF(next)
    setCursor(undefined)
  }
  return (
    <section>
      <SectionHead title={t('Cases')} className="mt-7" />
      <Card className="space-y-4 p-5">
        <Segmented<'disputed' | 'all'>
          label={t('Which bookings')}
          value={f.status === 'disputed' ? 'disputed' : 'all'}
          onChange={(v) => set({ ...f, status: v === 'disputed' ? 'disputed' : undefined })}
          options={[
            { value: 'disputed', label: t('Disputed') },
            { value: 'all', label: t('All') },
          ]}
        />
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            set({ ...f, member: draft.member.trim() || undefined, booking: draft.booking.trim() || undefined })
          }}
        >
          <Field label={t('Member id or email')} htmlFor={`${id}-member`}>
            <Input id={`${id}-member`} value={draft.member} autoComplete="off" onChange={(e) => setDraft({ ...draft, member: e.target.value })} />
          </Field>
          <Field label={t('Booking id')} htmlFor={`${id}-booking`}>
            <Input id={`${id}-booking`} value={draft.booking} autoComplete="off" onChange={(e) => setDraft({ ...draft, booking: e.target.value })} />
          </Field>
          <Check checked={f.claims === 'open'} onChange={(v) => set({ ...f, claims: v ? 'open' : undefined })} label={t('Only with open claims')} />
          <div className="flex items-end">
            <Button type="submit" variant="secondary">
              {t('Search')}
            </Button>
          </div>
        </form>
      </Card>
      {page.isError ? (
        <p className="t-sm mt-4 text-[var(--danger)]" role="alert">
          {messageOf(page.error)}
        </p>
      ) : items.length === 0 && !page.isPending ? (
        <p className="t-sm mt-4 text-[var(--ink-3)]">{t('No cases.')}</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((c) => (
            <li key={c.id}>
              <CaseCard c={c} />
            </li>
          ))}
        </ul>
      )}
      {page.data?.nextCursor && (
        <Button className="mt-3" variant="secondary" onClick={() => setCursor(page.data?.nextCursor)}>
          {t('Next page')}
        </Button>
      )}
    </section>
  )
}

function CaseCard({ c }: { c: CaseRow }) {
  return (
    <Card className="p-4">
      <p className="text-body font-semibold">
        <Link className="underline" to={`/admin/case/${c.id}`}>
          {c.title}
        </Link>
      </p>
      <p className="t-sm text-[var(--ink-3)]">
        {statusLabel(c.status)} · {formatMoney(c.amount, c.currency)} · {range(c.windowStart, c.windowEnd)}
      </p>
      <p className="t-sm text-[var(--ink-4)]">
        <Person id={c.requesterId} /> → <Person id={c.ownerId} /> · {t('changed {when}', { when: ago(c.updatedAt) })}
      </p>
      <div className="mt-2 flex flex-wrap gap-2 text-label font-semibold">
        {c.status === 'disputed' && c.dispute?.escalatedAt && <span className="text-[var(--danger)]">{t('Escalated to staff')}</span>}
        {/* Only while it is still open: a settled case has no offer on the table (V6-8). */}
        {c.status === 'disputed' && c.dispute?.offer && <span className="text-[var(--ink-2)]">{t('Offer on the table: {amount}', { amount: formatMoney(c.dispute.offer.refundAmount, c.currency) })}</span>}
        {c.pendingApproval && <span className="text-[var(--warn)]">{t('Waiting for approval')}</span>}
        {c.openClaims > 0 && <span className="text-[var(--warn)]">{plural(c.openClaims, '{n} open claim', '{n} open claims')}</span>}
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ approvals

/** Refunds above a staff member's limit wait here for a second one (four eyes, H-6). */
export function Approvals() {
  const qc = useQueryClient()
  const toast = useToast()
  const me = useSession()?.sub
  const pending = useQuery({ queryKey: ['adminResolutions'], queryFn: getPendingResolutions })
  const [open, setOpen] = useState<{ r: Resolution; approve: boolean } | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const attempt = useAttemptKey()
  const items = pending.data ?? []
  const decide = async () => {
    if (!open) return
    setBusy(true)
    try {
      if (open.approve) {
        const body = { id: open.r.id, note: note.trim() }
        await approveResolution(open.r.id, note.trim(), attempt.keyFor(body))
        attempt.settle()
        toast(t('Approved. The money moves now'))
      } else {
        await rejectResolution(open.r.id, note.trim())
        toast(t('Rejected. The booking stays in dispute'))
      }
      setOpen(null)
      setNote('')
    } catch (err) {
      attempt.settle(err)
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await Promise.all(['adminResolutions', 'adminCases', 'adminCase', 'audit'].map((k) => qc.invalidateQueries({ queryKey: [k] })))
    }
  }
  return (
    <section>
      <SectionHead title={t('Waiting for approval')} className="mt-7" />
      {pending.isError ? (
        <p className="t-sm text-[var(--danger)]" role="alert">
          {messageOf(pending.error)}
        </p>
      ) : items.length === 0 ? (
        <p className="t-sm py-4 text-[var(--ink-3)]">{t('Nothing waiting.')}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <li key={r.id}>
              <Card className="p-4">
                <p className="t-sm text-[var(--ink-3)]">
                  {r.title ?? r.bookingId}
                  {r.ownerName ? ` · ${r.ownerName}` : ''}
                </p>
                <p className="text-body font-semibold">
                  {t(OUTCOME_LABEL[r.outcome])}
                  {r.refundAmount ? ` · ${formatMoney(r.refundAmount, r.currency)}` : ''}
                </p>
                <p className="t-sm text-[var(--ink-3)]">
                  {reasonLabel(r.reasonCode)} · {r.by === me ? t('proposed by you') : t('proposed by {who}', { who: staff(r.by, me) })} · {ago(r.createdAt)}
                </p>
                {r.note && <p className="t-sm mt-1 text-[var(--ink-2)]">{r.note}</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" to={`/admin/case/${r.bookingId}`}>
                    {t('Open the case')}
                  </Button>
                  {r.by === me ? (
                    <WithdrawButton r={r} />
                  ) : (
                    <>
                      <Button size="sm" onClick={() => setOpen({ r, approve: true })}>
                        {t('Approve')}
                      </Button>
                      <Button size="sm" variant="quiet" onClick={() => setOpen({ r, approve: false })}>
                        {t('Reject')}
                      </Button>
                    </>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <Sheet
        open={Boolean(open)}
        onClose={() => setOpen(null)}
        title={open?.approve ? t('Approve this refund?') : t('Reject this refund?')}
        footer={
          <Button block size="lg" variant={open?.approve ? 'primary' : 'danger'} disabled={busy || note.trim().length < 5} onClick={() => void decide()}>
            {open?.approve ? t('Approve') : t('Reject')}
          </Button>
        }
      >
        <div className="pb-3">
          <Field label={t('Why')} htmlFor="approval-note" hint={t('Kept in the audit log. At least 5 characters.')}>
            <Textarea id="approval-note" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
      </Sheet>
    </section>
  )
}

// ------------------------------------------------------------------ audit log

const ACTION_LABEL: Record<string, string> = {
  dismiss: 'Dismissed',
  take_down: 'Taken down',
  suspend: 'Suspended',
  reinstate: 'Reinstated',
  remove_content: 'Removed',
  approve: 'Approved',
  resolve_dispute: 'Resolved a dispute',
  propose_resolution: 'Proposed a refund',
  approve_resolution: 'Approved a refund',
  reject_resolution: 'Rejected a refund',
  withdraw_resolution: 'Withdrew a refund proposal',
  confirm_claim: 'Confirmed a claim',
  reject_claim: 'Rejected a claim',
  read_case: 'Opened a case',
  read_evidence: 'Looked at hand-over photos',
}
const TARGET_LABEL: Record<string, string> = { listing: 'Listing', owner: 'Person', message: 'Message', review: 'Review', booking: 'Booking', resolution: 'Refund', claim: 'Claim' }

/** Every staff action, paged and filterable (H-7). */
export function AuditLog() {
  const id = useId()
  const me = useSession()?.sub
  const [f, setF] = useState<{ target?: string; actor?: string }>({})
  const [draft, setDraft] = useState({ target: '', actor: '' })
  const [pages, setPages] = useState<(string | undefined)[]>([undefined])
  return (
    <section>
      <SectionHead title={t('Audit log')} className="mt-7" />
      <Card className="p-5">
        <form
          className="mb-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault()
            setF({ target: draft.target.trim() || undefined, actor: draft.actor.trim() || undefined })
            setPages([undefined])
          }}
        >
          <Field label={t('About (booking, listing or person id)')} htmlFor={`${id}-target`}>
            <Input id={`${id}-target`} value={draft.target} autoComplete="off" onChange={(e) => setDraft({ ...draft, target: e.target.value })} />
          </Field>
          <Field label={t('By (staff id)')} htmlFor={`${id}-actor`}>
            <Input id={`${id}-actor`} value={draft.actor} autoComplete="off" onChange={(e) => setDraft({ ...draft, actor: e.target.value })} />
          </Field>
          <div className="flex items-end">
            <Button type="submit" variant="secondary">
              {t('Filter')}
            </Button>
          </div>
        </form>
        <ul className="space-y-3">
          {pages.map((cursor, i) => (
            <AuditPage
              key={cursor ?? 'first'}
              filters={f}
              cursor={cursor}
              me={me}
              onMore={i === pages.length - 1 ? (next) => setPages([...pages, next]) : undefined}
            />
          ))}
        </ul>
      </Card>
    </section>
  )
}

function AuditPage({
  filters,
  cursor,
  me,
  onMore,
}: {
  filters: { target?: string; actor?: string }
  cursor?: string
  me?: string
  onMore?: (next: string) => void
}) {
  const page = useQuery({ queryKey: ['audit', filters, cursor], queryFn: () => getAudit(filters, cursor) })
  if (page.isError)
    return (
      <li className="t-sm text-[var(--danger)]" role="alert">
        {messageOf(page.error)}
      </li>
    )
  const items = page.data?.items ?? []
  if (!cursor && items.length === 0 && !page.isPending) return <li className="t-sm text-[var(--ink-3)]">{t('No actions yet.')}</li>
  return (
    <>
      {items.map((a) => (
        <AuditLine key={a.id} a={a} me={me} />
      ))}
      {onMore && page.data?.nextCursor && (
        <li>
          <Button size="sm" variant="secondary" onClick={() => onMore(page.data!.nextCursor!)}>
            {t('Older')}
          </Button>
        </li>
      )}
    </>
  )
}

/** A booking action in words (V6-9): the listing, the outcome, the money, the
 *  reason, then staff's own note. Other actions show the server's statement. */
function auditText(a: AuditEntry): string {
  const d = a.details
  // Rows from before V6 answer `details: {}`: read their old machine line instead.
  if (!d || Object.keys(d).length === 0) return legacyAuditText(a.statement)
  const parts = [
    d.listingTitle,
    d.outcome ? t(OUTCOME_LABEL[d.outcome]) : '',
    d.amount ? formatMoney(d.amount, d.currency ?? 'EUR') : '',
    d.reasonCode ? reasonLabel(d.reasonCode) : '',
    d.claimKind === 'late_return' ? t('Late return') : '',
    // The claim's statement by code, in the reader's language (V8-11).
    d.noteCode === 'from_record' ? t('Confirmed from the booking record') : d.noteCode === 'not_supported' ? t('Not supported by the booking record') : '',
  ].filter(Boolean)
  const head = parts.join(' · ')
  return a.statement ? (head ? `${head}. ${a.statement}` : a.statement) : head
}

/** Rows written before `details` (V6-9) kept booking's machine lines:
 *  "<outcome> <minor> <CUR> (<reason>) <note>", "withdrew rs_…", "opened the case view". */
function legacyAuditText(statement: string): string {
  const m = /^(refund_buyer|partial|pay_owner) (\d+) ([A-Za-z]{3}) \((\w+)\)\s*([\s\S]*)$/.exec(statement)
  if (m) {
    const [, outcome, minor, cur, reason, note] = m
    const head = [t(OUTCOME_LABEL[outcome as ResolveOutcome]), Number(minor) > 0 ? formatMoney(Number(minor), cur) : '', reasonLabel(reason)].filter(Boolean).join(' · ')
    return note ? `${head}. ${note}` : head
  }
  if (/^(approved|rejected|withdrew) rs_\w+$/.test(statement) || statement === 'opened the case view') return ''
  if (statement === 'late_return') return t('Late return')
  return statement ? t(statement) : ''
}

function AuditLine({ a, me }: { a: AuditEntry; me?: string }) {
  const bookingLink = a.targetType === 'booking' ? `/admin/case/${a.targetId}` : null
  return (
    <li className="border-b border-[var(--line)] pb-3 last:border-0 last:pb-0">
      <p className="text-body font-semibold">
        {t(ACTION_LABEL[a.action] ?? a.action)} · {t(TARGET_LABEL[a.targetType] ?? a.targetType)}{' '}
        {/* Names and titles as the server knows them now, never a raw id (V8-11). */}
        {bookingLink ? (
          <Link className="underline" to={bookingLink}>
            {a.details?.listingTitle ?? a.details?.targetLabel ?? t('this booking')}
          </Link>
        ) : (
          <span className="text-[var(--ink-3)]">{a.details?.targetLabel ?? a.details?.personName ?? t('(no longer here)')}</span>
        )}
      </p>
      <p className="t-sm text-[var(--ink-4)]">
        {a.actorId === me ? t('by you') : t('by {who}', { who: staff(a.actorId, me) })} · {ago(a.at)}
        {a.reportId ? ` · ${t('report {id}', { id: a.reportId })}` : ''}
      </p>
      {/* The server's own statements ("Checked and approved") in the reader's language (V5-18), and
          its machine lines ("partial 1500 EUR (damage) …") in words (V6-9). */}
      {auditText(a) && <p className="t-sm mt-1 text-[var(--ink-2)]">{auditText(a)}</p>}
    </li>
  )
}

// ------------------------------------------------------------------ one case

/** One booking as staff see it: everything needed to decide, on one page (H-9). */
export function AdminCase() {
  const { id = '' } = useParams()
  const session = useSession()
  // Every fetch is an audited opening (H-7): refetch on purpose, not on focus or remount (V6-9).
  const kase = useQuery({ queryKey: ['adminCase', id], queryFn: () => getCase(id), enabled: Boolean(session?.staff), staleTime: 5 * 60_000, refetchOnWindowFocus: false })
  if (!session?.staff)
    return (
      <Screen back="/admin" title={t('Case')}>
        <p className="t-sm text-[var(--ink-3)]">{t('Only for Cappy staff')}</p>
      </Screen>
    )
  if (kase.isPending) return <Screen back="/admin">{null}</Screen>
  if (kase.isError)
    return (
      <Screen back="/admin" title={t('Case')}>
        <p className="t-sm text-[var(--danger)]" role="alert">
          {messageOf(kase.error)}
        </p>
      </Screen>
    )
  const c = kase.data
  const b = c.booking
  const cur = b.currency ?? 'EUR'
  const title = b.listing?.title ?? b.match.listingId
  const me = session.sub
  const pendingOne = c.resolutions.find((r) => r.status === 'pending_approval')
  return (
    <Screen back="/admin" title={title}>
      <p className="t-sm -mt-2 mb-5 text-[var(--ink-3)]">
        {statusLabel(b.status)} · {range(b.match.start, b.match.end)} · {formatMoney(b.match.quote.total, cur)} · <span className="tnum">{b.id}</span>
      </p>
      <Button size="sm" variant="secondary" to={`/admin/listing/${b.match.listingId}`}>
        {t('Open the listing (staff view)')}
      </Button>

      {/* Only while it is open: a settled dispute is told by its refund decision below. */}
      {c.dispute && b.status === 'disputed' && (
        <Banner
          tone={c.dispute.escalatedAt ? 'danger' : 'warn'}
          title={c.dispute.escalatedAt ? t('Escalated: the parties did not agree in time') : t('In dispute')}
          body={`${t('Reported by {who} {when}: {reason}', { who: c.dispute.openedBy === c.requesterId ? t('the renter') : t('the owner'), when: ago(c.dispute.openedAt), reason: c.dispute.reason })}${
            c.dispute.offer
              ? ` ${t('Offer on the table: {amount}, from the {side}.', {
                  amount: formatMoney(c.dispute.offer.refundAmount, cur),
                  side: c.dispute.offer.by === c.requesterId ? t('renter') : t('owner'),
                })}`
              : ''
          }`}
        />
      )}

      <Card className="mt-4 p-5">
        <h2 className="t-label mb-2">{t('People')}</h2>
        <Row label={t('Renter')} value={<Person id={c.requesterId} />} />
        <Row label={t('Owner')} value={<Person id={c.ownerId} />} />
      </Card>

      {/* One decision at a time (V6-10): while a proposal waits, it stands in for the form. */}
      {b.status === 'disputed' &&
        (pendingOne ? (
          <Card className="mt-4 p-5">
            <h2 className="t-label mb-2">{t('Decide')}</h2>
            <p className="t-sm text-[var(--ink-2)]">
              {t('A proposal is waiting for a second staff member: {what}. Nothing else can be decided until it is approved, rejected or withdrawn.', {
                what: [t(OUTCOME_LABEL[pendingOne.outcome]), pendingOne.refundAmount ? formatMoney(pendingOne.refundAmount, pendingOne.currency) : ''].filter(Boolean).join(' · '),
              })}
            </p>
            <div className="mt-3">
              <WithdrawButton r={pendingOne} />
            </div>
          </Card>
        ) : (
          <ResolveForm bookingId={b.id} amount={b.match.quote.total} currency={cur} />
        ))}

      {c.resolutions.length > 0 && (
        <>
          <SectionHead title={t('Decisions')} className="mt-7" />
          <Card className="space-y-3 p-5">
            {c.resolutions.map((r) => (
              <div key={r.id} className="border-b border-[var(--line)] pb-3 last:border-0 last:pb-0">
                <p className="text-body font-semibold">
                  {t(OUTCOME_LABEL[r.outcome])}
                  {r.refundAmount ? ` · ${formatMoney(r.refundAmount, r.currency)}` : ''} · {t(RESOLUTION_STATUS[r.status])}
                </p>
                <p className="t-sm text-[var(--ink-3)]">
                  {r.role === 'parties' ? t('agreed by the parties') : `${reasonLabel(r.reasonCode)} · ${staff(r.by, me)}`} · {ago(r.createdAt)}
                  {r.approvedBy ? ` · ${r.approvedBy === me ? t('approved by you') : t('approved by {who}', { who: staff(r.approvedBy, me) })}` : ''}
                </p>
                {r.note && <p className="t-sm mt-1 text-[var(--ink-2)]">{r.note}</p>}
                <div className="mt-2">
                  <WithdrawButton r={r} />
                </div>
              </div>
            ))}
          </Card>
        </>
      )}

      {c.claims.length > 0 && <Claims claims={c.claims} bookingId={b.id} />}

      <SectionHead title={t('Timeline')} className="mt-7" />
      <Card className="p-5">
        <ol className="space-y-2">
          {/* Status steps and the claims' own moments, in time order (V9-13). */}
          {[
            ...c.timeline.map((e) => ({
              at: e.at,
              text: `${e.fromStatus ? `${statusLabel(e.fromStatus)} → ` : ''}${statusLabel(e.toStatus)} · ${actorLabel(e, c, me)}`,
            })),
            ...c.claims.flatMap((cl) => [
              { at: cl.createdAt, text: `${t('Late return reported: {n} minutes', { n: cl.minutesLate })} · ${t('Owner')}` },
              ...(cl.decidedAt
                ? [{ at: cl.decidedAt, text: `${cl.status === 'confirmed' ? t('Claim confirmed') : t('Claim rejected')} · ${staff(cl.decidedBy ?? '', me)}` }]
                : []),
            ]),
          ]
            .sort((x, y) => Date.parse(x.at) - Date.parse(y.at))
            .map((e, i) => (
              <li key={i} className="t-sm text-[var(--ink-2)]">
                <span className="tnum text-[var(--ink-4)]">{when(e.at)}</span> · {e.text}
              </li>
            ))}
        </ol>
      </Card>

      <SectionHead title={t('Conversation, as written')} className="mt-7" />
      <Card className="p-5">
        {c.messages.length === 0 ? (
          <p className="t-sm text-[var(--ink-3)]">{t('No messages.')}</p>
        ) : (
          <ul className="space-y-3">
            {c.messages.map((m) => (
              <li key={m.id}>
                <p className="t-sm text-[var(--ink-4)]">
                  {m.senderId === c.requesterId ? t('Renter') : t('Owner')} · {when(m.at)}
                  {m.flagged ? ` · ${t('flagged: paying outside Cappy')}` : ''}
                </p>
                <p className="whitespace-pre-wrap text-body text-[var(--ink)]">{m.body}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <SectionHead title={t('Hand-over photos')} className="mt-7" />
      <Card className="p-5">
        {c.evidence.length === 0 ? (
          <p className="t-sm text-[var(--ink-3)]">{t('No photos.')}</p>
        ) : (
          c.evidence.map((e) => (
            <div key={e.id} className="mb-4 last:mb-0">
              <p className="t-sm text-[var(--ink-4)]">
                {e.stage === 'check_in' ? t('Check-in') : t('Check-out')} · {e.by === c.requesterId ? t('renter') : t('owner')} · {when(e.at)}
              </p>
              {e.note && <p className="t-sm text-[var(--ink-2)]">{e.note}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                {e.photos.map((src, i) => (
                  <a key={i} href={src} target="_blank" rel="noopener noreferrer">
                    <img src={src} alt={t('Photo {n}', { n: i + 1 })} className="h-24 w-24 rounded-[var(--radius-control)] object-cover" />
                  </a>
                ))}
              </div>
            </div>
          ))
        )}
      </Card>

      {c.payment && (
        <>
          <SectionHead title={t('Payment')} className="mt-7" />
          <Card className="p-5">
            <Row label={t('Status')} value={t(PAYMENT_STATUS[c.payment.status] ?? c.payment.status)} />
            <Row label={t('Amount')} value={formatMoney(c.payment.amount, c.payment.currency)} />
            <Row label={t('Captured')} value={formatMoney(c.payment.captured, c.payment.currency)} />
            <Row label={t('Refunded')} value={formatMoney(c.payment.refunded, c.payment.currency)} />
            <Row label={t('Paid out to the owner')} value={formatMoney(c.payment.paidOut, c.payment.currency)} />
            {c.payment.chargebackAt && <Row label={t('Chargeback')} value={when(c.payment.chargebackAt)} />}
          </Card>
        </>
      )}
    </Screen>
  )
}

/** Refund all, part, or pay the owner, always with a reason (H-6, V5-8). Over the
 *  staff member's limit it waits for a second one. */
function ResolveForm({ bookingId, amount, currency }: { bookingId: string; amount: number; currency: string }) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [outcome, setOutcome] = useState<ResolveOutcome>('partial')
  const [refund, setRefund] = useState('')
  const [reason, setReason] = useState<ReasonCode | ''>('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const attempt = useAttemptKey()
  const minor = outcome === 'partial' ? toMinor(refund, currency) : undefined
  const refundBad = outcome === 'partial' && (minor === null || minor === undefined || minor <= 0 || minor >= amount)
  const ready = reason && note.trim().length >= 10 && !refundBad
  const submit = async () => {
    if (!reason) return
    setBusy(true)
    const body = { outcome, reasonCode: reason, note: note.trim(), ...(outcome === 'partial' ? { refundAmount: minor! } : {}) }
    try {
      const out = await resolveDispute(bookingId, body, attempt.keyFor(body))
      attempt.settle()
      toast(out.resolution.status === 'pending_approval' ? t('Above your limit: it waits for a second staff member') : t('Decided. Both sides have been told'))
    } catch (err) {
      attempt.settle(err)
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await Promise.all(['adminCase', 'adminCases', 'adminResolutions', 'audit'].map((k) => qc.invalidateQueries({ queryKey: [k] })))
    }
  }
  return (
    <>
      <SectionHead title={t('Decide the dispute')} className="mt-7" />
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('Outcome')}>
          {(['refund_buyer', 'partial', 'pay_owner'] as ResolveOutcome[]).map((o) => (
            <Button key={o} size="sm" variant={o === outcome ? 'ink' : 'secondary'} aria-pressed={o === outcome} onClick={() => setOutcome(o)}>
              {t(OUTCOME_LABEL[o])}
            </Button>
          ))}
        </div>
        {outcome === 'partial' && (
          <Field
            label={t('Refund to the renter')}
            htmlFor={`${id}-refund`}
            error={refund && refundBad ? t('More than nothing and less than {total}.', { total: formatMoney(amount, currency) }) : undefined}
            hint={t('Of {total}. The owner is paid the rest, less the fee.', { total: formatMoney(amount, currency) })}
          >
            <Input id={`${id}-refund`} inputMode="decimal" value={refund} invalid={Boolean(refund && refundBad)} onChange={(e) => setRefund(e.target.value)} />
          </Field>
        )}
        <Field label={t('Reason')} htmlFor={`${id}-reason`}>
          <Select id={`${id}-reason`} value={reason} onChange={(e) => setReason(e.target.value as ReasonCode)}>
            <option value="">{t('Choose a reason')}</option>
            {REASON_CODES.map(([k, label]) => (
              <option key={k} value={k}>
                {t(label)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('What you found')} htmlFor={`${id}-note`} hint={t('Sent to both sides with the decision. At least 10 characters.')}>
          <Textarea id={`${id}-note`} rows={4} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Button disabled={busy || !ready} onClick={() => void submit()}>
          {busy ? t('One moment…') : t('Decide')}
        </Button>
      </Card>
    </>
  )
}

/** Late-return claims (S-12): staff confirm or reject; nothing is charged yet (S-9). */
function Claims({ claims, bookingId }: { claims: Claim[]; bookingId: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const decide = async (c: Claim, decision: 'confirm' | 'reject') => {
    setBusy(c.id)
    try {
      // A code, so every reader gets the statement in their language (V8-11).
      await decideClaim(c.id, decision, decision === 'confirm' ? 'from_record' : 'not_supported')
      toast(decision === 'confirm' ? t('Claim confirmed') : t('Claim rejected'))
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(null)
      await qc.invalidateQueries({ queryKey: ['adminCase', bookingId] })
      await qc.invalidateQueries({ queryKey: ['audit'] })
    }
  }
  return (
    <>
      <SectionHead title={t('Claims')} className="mt-7" />
      <Card className="space-y-3 p-5">
        {claims.map((c) => (
          <div key={c.id} className="border-b border-[var(--line)] pb-3 last:border-0 last:pb-0">
            <p className="text-body font-semibold">
              {t('Late return: {n} minutes', { n: c.minutesLate })} · {formatMoney(c.amount, c.currency)} · {t(CLAIM_STATUS[c.status])}
            </p>
            {c.note && <p className="t-sm text-[var(--ink-2)]">{c.note}</p>}
            <p className="t-sm text-[var(--ink-4)]">{ago(c.createdAt)}</p>
            {c.status === 'open' && (
              <div className="mt-2 flex gap-2">
                <Button size="sm" disabled={busy === c.id} onClick={() => void decide(c, 'confirm')}>
                  {t('Confirm')}
                </Button>
                <Button size="sm" variant="quiet" disabled={busy === c.id} onClick={() => void decide(c, 'reject')}>
                  {t('Reject')}
                </Button>
              </div>
            )}
          </div>
        ))}
        {/* The hint is for deciding; once decided it would read as if pending (V8-15). */}
        {claims.some((c) => c.status === 'open') && (
          <p className="t-sm text-[var(--ink-4)]">{t('Confirming records the claim; nothing is charged to the renter yet.')}</p>
        )}
      </Card>
    </>
  )
}
export const CLAIM_STATUS: Record<Claim['status'], string> = { open: 'Open', confirmed: 'Confirmed', rejected: 'Rejected' }

// ------------------------------------------------------------ listing preview

const STATE_LABEL: Record<string, string> = {
  live: 'Live: everyone can see it',
  held: 'Held: waiting for a quick check',
  paused: 'Paused by its owner',
  taken_down: 'Taken down',
  deleted: 'Deleted',
}
const HOLD_LABEL: Record<string, string> = {
  market_not_live: 'In a country where Cappy is not open yet',
  district_not_in_country: "In a district outside its owner's country",
}

/** Any listing as staff see it, whatever its state, so approvals are never blind (V5-4). */
export function AdminListing() {
  const { id = '' } = useParams()
  const session = useSession()
  const qc = useQueryClient()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const q = useQuery({ queryKey: ['adminListing', id], queryFn: () => getAdminListing(id), enabled: Boolean(session?.staff) })
  if (!session?.staff)
    return (
      <Screen back="/admin" title={t('Listing')}>
        <p className="t-sm text-[var(--ink-3)]">{t('Only for Cappy staff')}</p>
      </Screen>
    )
  if (q.isPending) return <Screen back="/admin">{null}</Screen>
  if (q.isError)
    return (
      <Screen back="/admin" title={t('Listing')}>
        <p className="t-sm text-[var(--danger)]" role="alert">
          {messageOf(q.error)}
        </p>
      </Screen>
    )
  const { detail, state, holdReason, heldAt, handover, reviews } = q.data
  // A hold for where it is (V5-1) is lifted by the owner moving it, never by approval.
  const approvable = state === 'held' && !holdReason
  const approve = async () => {
    setBusy(true)
    try {
      await approveListing(id)
      toast(t('Approved: it is live now'))
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await Promise.all(['adminListing', 'adminHeld'].map((k) => qc.invalidateQueries({ queryKey: [k] })))
    }
  }
  const banner = (
    <Banner
      tone={state === 'live' ? 'accent' : 'warn'}
      title={`${t('Staff view')} · ${t(STATE_LABEL[state] ?? state)}`}
      body={[holdReason ? t(HOLD_LABEL[holdReason] ?? holdReason) : '', heldAt ? t('Held {when}', { when: ago(heldAt) }) : ''].filter(Boolean).join(' · ') || t('Read-only: nothing can be booked from here.')}
      action={
        approvable ? (
          <Button size="sm" disabled={busy} onClick={() => void approve()}>
            {t('Approve')}
          </Button>
        ) : undefined
      }
    />
  )
  const address = [handover?.address, handover?.postalCode].filter(Boolean).join(', ') || undefined
  // Availability only for what could be booked: live, or held for a price check (not for where it is).
  const bookable = state === 'live' || (state === 'held' && !holdReason)
  return <Listing preview={{ detail, banner, address, reviews, bookable }} />
}
