import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { confirmTotp, startTotp, useAuthReady, useSession } from '../../data/auth.ts'
import {
  ApiError,
  approveListing,
  decideReport,
  getHeldListings,
  getAdminReports,
  reinstateOwner,
  resolveDispute,
  suspendOwner,
  takeDownListing,
  useAudit,
  REPORT_REASONS,
  type Decision,
  type Grounds,
  type Report,
} from '../../data/repo.ts'
import { formatMoney } from '../../domain/money.ts'
import { messageOf, useToast } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { SignedOut } from '../components/SignedOut.tsx'
import { Button, Card, Check, EmptyState, Field, Input, Segmented, Sheet, Textarea } from '../components/ui.tsx'
import { ago } from '../format.ts'
import { t } from '../../i18n.ts'

type Status = Report['status']
type Action = Decision
const ACTION_LABEL: Record<Action, string> = {
  dismiss: 'Dismiss',
  take_down: 'Take the listing down',
  suspend: 'Suspend the owner',
  remove_content: 'Remove it',
}
/** What each action is called for each kind of report (FL-7): a message or a
 *  review is removed, and suspending hits its author, not a listing's owner. */
function actionLabel(a: Action, target: Report['targetType'] | undefined): string {
  if (a === 'remove_content') return target === 'review' ? 'Remove the review' : 'Remove the message'
  if (a === 'suspend' && (target === 'message' || target === 'review')) return 'Suspend the author'
  if (a === 'suspend' && target === 'owner') return 'Suspend this person'
  return ACTION_LABEL[a]
}

const REASON_LABEL: Record<string, string> = {
  ...Object.fromEntries(REPORT_REASONS),
  reliability: 'Reliability: repeated cancellations or no-shows',
  linked_to_suspended: 'Paid with a card a suspended account used',
}
const TARGET_LABEL: Record<string, string> = { listing: 'Listing', owner: 'Person', message: 'Message', review: 'Review', booking: 'Booking' }
/** Decisions and audit entries in words, not codes (V4-15). */
const DONE_LABEL: Record<string, string> = {
  dismiss: 'Dismissed',
  take_down: 'Taken down',
  suspend: 'Suspended',
  reinstate: 'Reinstated',
  remove_content: 'Removed',
  approve: 'Approved',
  pay_owner: 'Paid the owner',
  refund_buyer: 'Refunded the buyer',
  resolve: 'Resolved',
}
const doneLabel = (a?: string) => (a ? t(DONE_LABEL[a] ?? a) : '')
const targetLabel = (k: string) => t(TARGET_LABEL[k] ?? k)

/** The rule or law a decision rests on (DSA Art. 17(3)(d)); terms by default. */
function GroundsFields({ value, onChange, id }: { value: Grounds; onChange: (g: Grounds) => void; id: string }) {
  return (
    <>
      <Field label={t('Based on')}>
        <Segmented<'terms' | 'law'>
          label={t('Based on')}
          value={value.ground}
          onChange={(ground) => onChange({ ...value, ground })}
          options={[
            { value: 'terms', label: t('Our terms') },
            { value: 'law', label: t('The law') },
          ]}
        />
      </Field>
      <Field label={t('Which rule (optional)')} htmlFor={`${id}-clause`} hint={t('Left empty, the statement names our rules for listings and conduct, or the applicable law.')}>
        <Input
          id={`${id}-clause`}
          maxLength={200}
          value={value.clause ?? ''}
          onChange={(e) => onChange({ ...value, clause: e.target.value })}
        />
      </Field>
      <Check
        checked={value.automated}
        onChange={(automated) => onChange({ ...value, automated })}
        label={t('Detected or decided automatically')}
        hint={t('The statement must say so when a machine found or decided it.')}
      />
    </>
  )
}
const noGrounds: Grounds = { ground: 'terms', clause: '', automated: false }
const clean = (g: Grounds): Grounds => ({ ground: g.ground, automated: g.automated, ...(g.clause?.trim() ? { clause: g.clause.trim() } : {}) })

/** Where the reported thing lives, for a staff member to look at it. */
function targetLink(r: Report): string | null {
  if (r.targetType === 'listing') return `/listing/${r.targetId}`
  return null
}

/**
 * The staff console: the report queue (DSA Art. 16), decisions with a statement
 * of reasons (Art. 17), direct actions and the audit log. The menu shows only
 * for staff, but every call here is checked by the server: this page grants nothing.
 */
export function Admin() {
  const session = useSession()
  const ready = useAuthReady()
  if (ready && !session) {
    return (
      <Screen title={t('Staff console')}>
        <SignedOut what={t('use the staff console')} next="/admin" />
      </Screen>
    )
  }
  if (!ready) return <Screen title={t('Staff console')}>{null}</Screen>
  if (!session?.staff) {
    return (
      <Screen title={t('Staff console')}>
        <EmptyState
          icon="shield"
          title={t('Only for Cappy staff')}
          body={t('This account is not in the staff group. If you should have access, ask an administrator.')}
        />
      </Screen>
    )
  }
  return <Console />
}

/** Staff powers need two-step sign-in (P-3): until it is on, the server answers
 *  every staff call with `mfa_required`, and this page sets it up. */
function Console() {
  const probe = useQuery({ queryKey: ['adminReports', 'open', undefined], queryFn: () => getAdminReports('open') })
  const mfa = probe.error instanceof ApiError && probe.error.code === 'mfa_required'
  return (
    <Screen title={t('Staff console')}>
      {mfa ? (
        <TotpSetup onDone={() => void probe.refetch()} />
      ) : (
        <>
          <Queue />
          <Held />
          <Actions />
          <Audit />
        </>
      )}
    </Screen>
  )
}

function TotpSetup({ onDone }: { onDone: () => void }) {
  const toast = useToast()
  const [secret, setSecret] = useState<{ secret: string; uri: string } | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (step: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await step()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('That did not work. Try again.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="p-5">
      <h2 className="t-h3">{t('Set up two-step sign-in')}</h2>
      <p className="t-sm mt-2 text-[var(--ink-3)]">
        {t('Staff can move money and suspend people, so a password alone is not enough. Add Cappy to an authenticator app; from then on each sign-in asks for its code.')}
      </p>
      {!secret ? (
        <Button className="mt-4" disabled={busy} onClick={() => void run(async () => setSecret(await startTotp()))}>
          {busy ? t('One moment…') : t('Start')}
        </Button>
      ) : (
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              await confirmTotp(code)
              toast(t('Two-step sign-in is on'))
              onDone()
            })
          }}
        >
          {/* ponytail: no QR library installed; the otpauth link opens the authenticator on a phone, the key is typed on a computer. */}
          <p className="t-sm">
            <a href={secret.uri} className="font-semibold underline">
              {t('Open in your authenticator app')}
            </a>
          </p>
          <Field label={t('Or enter this key')} htmlFor="totp-secret">
            <Input id="totp-secret" readOnly value={secret.secret} className="font-mono" onFocus={(e) => e.currentTarget.select()} />
          </Field>
          <Field label={t('Code from the app')} htmlFor="totp-code">
            <Input
              id="totp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
            />
          </Field>
          <Button type="submit" disabled={busy || code.length !== 6}>
            {busy ? t('One moment…') : t('Turn on two-step sign-in')}
          </Button>
        </form>
      )}
      {error && (
        <p role="alert" className="t-sm mt-3 font-semibold text-[var(--danger)]">
          {error}
        </p>
      )}
    </Card>
  )
}

function Queue() {
  const [status, setStatus] = useState<Status>('open')
  const [cursor, setCursor] = useState<string | undefined>()
  const [deciding, setDeciding] = useState<Report | null>(null)
  const page = useQuery({
    queryKey: ['adminReports', status, cursor],
    queryFn: () => getAdminReports(status, cursor),
  })
  const items = page.data?.items ?? []
  return (
    <section>
      <SectionHead title={t('Reports')} />
      <Segmented
        label={t('Which reports')}
        value={status}
        onChange={(v) => {
          setStatus(v)
          setCursor(undefined)
        }}
        options={[
          { value: 'open', label: t('Open') },
          { value: 'actioned', label: t('Actioned') },
          { value: 'dismissed', label: t('Dismissed') },
        ]}
      />
      {page.isError ? (
        <p className="t-sm mt-4 text-[var(--danger)]" role="alert">
          {messageOf(page.error)}
        </p>
      ) : items.length === 0 && !page.isPending ? (
        <p className="t-sm mt-4 text-[var(--ink-3)]">{t('Nothing here.')}</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((r) => {
            const link = targetLink(r)
            return (
              <li key={r.id}>
                <Card className="p-4">
                  <p className="text-[0.9375rem] font-semibold">
                    {t(REASON_LABEL[r.reason] ?? r.reason)} · {targetLabel(r.targetType)}{' '}
                    {link ? (
                      <Link className="underline" to={link}>
                        {r.targetId}
                      </Link>
                    ) : (
                      <span className="tnum text-[var(--ink-3)]">{r.targetId}</span>
                    )}
                  </p>
                  <p className="t-sm text-[var(--ink-4)]">
                    {r.id} · {ago(r.createdAt)}
                  </p>
                  <p className="t-body mt-2 whitespace-pre-wrap text-[var(--ink-2)]">{r.details}</p>
                  {r.statement && (
                    <p className="t-sm mt-2 text-[var(--ink-3)]">
                      {t('Decided')}: {doneLabel(r.decision)} — {r.statement}
                    </p>
                  )}
                  {r.statementOfReasons && (
                    <p className="t-sm mt-1 text-[var(--ink-4)]">
                      {r.statementOfReasons.ground === 'law' ? t('The law') : t('Our terms')}: {r.statementOfReasons.clause}
                      {r.statementOfReasons.automated ? ` · ${t('automated')}` : ''}
                    </p>
                  )}
                  {r.status === 'open' && (
                    <div className="mt-3">
                      <Button size="sm" variant="secondary" onClick={() => setDeciding(r)}>
                        {t('Decide')}
                      </Button>
                    </div>
                  )}
                </Card>
              </li>
            )
          })}
        </ul>
      )}
      {page.data?.nextCursor && (
        <Button className="mt-3" variant="secondary" onClick={() => setCursor(page.data?.nextCursor)}>
          {t('Next page')}
        </Button>
      )}
      {/* Keyed by report: each one opens at Dismiss with an empty statement, never
          with the last report's decision armed (V4-2). */}
      <Decide key={deciding?.id ?? 'none'} report={deciding} onClose={() => setDeciding(null)} />
    </section>
  )
}

function Decide({ report, onClose }: { report: Report | null; onClose: () => void }) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [action, setAction] = useState<Action>('dismiss')
  const [statement, setStatement] = useState('')
  const [grounds, setGrounds] = useState(noGrounds)
  const [busy, setBusy] = useState(false)
  const short = statement.trim().length < 20
  const submit = async () => {
    if (!report) return
    setBusy(true)
    try {
      await decideReport(report.id, action, statement.trim(), clean(grounds))
      toast(t('Decided. The people concerned have been told'))
      setStatement('')
      setGrounds(noGrounds)
      onClose()
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await qc.invalidateQueries({ queryKey: ['adminReports'] })
      await qc.invalidateQueries({ queryKey: ['audit'] })
    }
  }
  const actions: Action[] =
    report?.targetType === 'listing'
      ? ['dismiss', 'take_down', 'suspend']
      : report?.targetType === 'message' || report?.targetType === 'review'
        ? ['dismiss', 'remove_content', 'suspend']
        : ['dismiss', 'suspend']
  return (
    <Sheet
      open={Boolean(report)}
      onClose={onClose}
      title={t('Decide on this report')}
      footer={
        <Button block size="lg" disabled={busy || short} onClick={() => void submit()}>
          {t(actionLabel(action, report?.targetType))}
        </Button>
      }
    >
      <div className="space-y-4 pb-3">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('Decision')}>
          {actions.map((a) => (
            <Button key={a} size="sm" variant={a === action ? 'ink' : 'secondary'} aria-pressed={a === action} onClick={() => setAction(a)}>
              {t(actionLabel(a, report?.targetType))}
            </Button>
          ))}
        </div>
        <Field
          label={t('Statement of reasons')}
          htmlFor={`${id}-why`}
          hint={t('Sent to the person affected and the reporter: what was decided, the facts, and the rule or law it rests on. At least 20 characters.')}
        >
          <Textarea id={`${id}-why`} rows={5} maxLength={2000} value={statement} onChange={(e) => setStatement(e.target.value)} />
        </Field>
        {action !== 'dismiss' && <GroundsFields id={id} value={grounds} onChange={setGrounds} />}
      </div>
    </Sheet>
  )
}

/** Held listings (FL-5): new owners' expensive listings wait for a look before
 *  anyone can book them. Approving puts them live; taking one down is below. */
function Held() {
  const qc = useQueryClient()
  const toast = useToast()
  const held = useQuery({ queryKey: ['adminHeld'], queryFn: getHeldListings })
  const [busy, setBusy] = useState<string | null>(null)
  const items = held.data ?? []
  const approve = async (id: string) => {
    setBusy(id)
    try {
      await approveListing(id)
      toast(t('Approved: it is live now'))
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(null)
      await qc.invalidateQueries({ queryKey: ['adminHeld'] })
      await qc.invalidateQueries({ queryKey: ['audit'] })
    }
  }
  return (
    <section>
      <SectionHead title={t('Waiting for a check')} className="mt-7" />
      {held.isError ? (
        <p className="t-sm text-[var(--danger)]" role="alert">
          {messageOf(held.error)}
        </p>
      ) : items.length === 0 ? (
        <p className="t-sm text-[var(--ink-3)]">{t('No listings are waiting.')}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((h) => (
            <li key={h.id}>
              <Card className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="text-[0.9375rem] font-semibold">
                    <Link className="underline" to={`/listing/${h.id}`}>
                      {h.title}
                    </Link>
                  </p>
                  <p className="t-sm text-[var(--ink-4)]">
                    {/* ponytail: the held list carries no currency yet; EUR until M-3. */}
                    {t('{price} / hour', { price: formatMoney(h.ratePerHour, 'EUR') })} · {h.ownerId} · {ago(h.heldAt)}
                  </p>
                </div>
                <Button size="sm" disabled={busy === h.id} onClick={() => void approve(h.id)}>
                  {busy === h.id ? t('One moment…') : t('Approve')}
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

type Direct = 'take_down' | 'suspend' | 'reinstate' | 'pay_owner' | 'refund_buyer'
const DIRECT: Record<Direct, { label: string; target: string; needsWhy: boolean }> = {
  take_down: { label: 'Take a listing down', target: 'Listing id', needsWhy: true },
  suspend: { label: 'Suspend an owner', target: 'Owner id', needsWhy: true },
  reinstate: { label: 'Reinstate an owner', target: 'Owner id', needsWhy: true },
  pay_owner: { label: 'Resolve dispute: pay the owner', target: 'Booking id', needsWhy: false },
  refund_buyer: { label: 'Resolve dispute: refund the buyer', target: 'Booking id', needsWhy: false },
}

function Actions() {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [kind, setKind] = useState<Direct>('take_down')
  const [target, setTarget] = useState('')
  const [statement, setStatement] = useState('')
  const [grounds, setGrounds] = useState(noGrounds)
  const [busy, setBusy] = useState(false)
  const spec = DIRECT[kind]
  const ready = target.trim() && (!spec.needsWhy || statement.trim().length >= 20)
  const run = async () => {
    setBusy(true)
    const to = target.trim()
    const why = statement.trim()
    try {
      if (kind === 'take_down') await takeDownListing(to, why, clean(grounds))
      else if (kind === 'suspend') await suspendOwner(to, why, clean(grounds))
      else if (kind === 'reinstate') await reinstateOwner(to, why)
      else await resolveDispute(to, kind)
      toast(t('Done'))
      setTarget('')
      setStatement('')
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await qc.invalidateQueries({ queryKey: ['audit'] })
    }
  }
  return (
    <section>
      <SectionHead title={t('Act directly')} className="mt-7" />
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('Action')}>
          {(Object.keys(DIRECT) as Direct[]).map((k) => (
            <Button key={k} size="sm" variant={k === kind ? 'ink' : 'secondary'} aria-pressed={k === kind} onClick={() => setKind(k)}>
              {t(DIRECT[k].label)}
            </Button>
          ))}
        </div>
        <Field label={t(spec.target)} htmlFor={`${id}-target`}>
          <Input id={`${id}-target`} value={target} onChange={(e) => setTarget(e.target.value)} autoComplete="off" />
        </Field>
        {spec.needsWhy && (
          <Field label={t('Statement of reasons')} htmlFor={`${id}-why`} hint={t('Sent to the person affected. At least 20 characters.')}>
            <Textarea id={`${id}-why`} rows={4} maxLength={2000} value={statement} onChange={(e) => setStatement(e.target.value)} />
          </Field>
        )}
        {(kind === 'take_down' || kind === 'suspend') && <GroundsFields id={id} value={grounds} onChange={setGrounds} />}
        <Button disabled={busy || !ready} onClick={() => void run()}>
          {t(spec.label)}
        </Button>
      </Card>
    </section>
  )
}

function Audit() {
  const audit = useAudit()
  const me = useSession()?.sub
  // ponytail: staff are named by the start of their id until the audit log carries a name or email.
  const who = (id: string) => (id === me ? t('you') : `${t('staff')} ${id.slice(0, 8)}`)
  return (
    <section>
      <SectionHead title={t('Audit log')} className="mt-7" />
      <Card className="p-5">
        {(audit.data ?? []).length === 0 ? (
          <p className="t-sm text-[var(--ink-3)]">{t('No actions yet.')}</p>
        ) : (
          <ul className="space-y-3">
            {audit.data!.map((a) => (
              <li key={a.id} className="border-b border-[var(--line)] pb-3 last:border-0 last:pb-0">
                <p className="text-[0.9062rem] font-semibold">
                  {doneLabel(a.action)} · {targetLabel(a.targetType)} <span className="tnum text-[var(--ink-3)]">{a.targetId}</span>
                </p>
                <p className="t-sm text-[var(--ink-4)]">
                  {t('by {who}', { who: who(a.actorId) })} · {ago(a.at)}
                  {a.reportId ? ` · ${t('report {id}', { id: a.reportId })}` : ''}
                </p>
                <p className="t-sm mt-1 text-[var(--ink-2)]">{a.statement}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}
