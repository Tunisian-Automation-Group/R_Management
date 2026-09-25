import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthReady, useSession } from '../../data/auth.ts'
import {
  decideReport,
  getAdminReports,
  reinstateOwner,
  resolveDispute,
  suspendOwner,
  takeDownListing,
  useAudit,
  type Report,
} from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { SignedOut } from '../components/SignedOut.tsx'
import { Button, Card, EmptyState, Field, Input, Segmented, Sheet, Textarea } from '../components/ui.tsx'
import { ago } from '../format.ts'
import { t } from '../../i18n.ts'

type Status = Report['status']
type Action = 'dismiss' | 'take_down' | 'suspend'
const ACTION_LABEL: Record<Action, string> = { dismiss: 'Dismiss', take_down: 'Take the listing down', suspend: 'Suspend the owner' }

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
  return (
    <Screen title={t('Staff console')}>
      <Queue />
      <Actions />
      <Audit />
    </Screen>
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
                  <p className="text-[15px] font-semibold">
                    {r.reason} · {r.targetType}{' '}
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
                      {t('Decided')}: {r.decision} — {r.statement}
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
      <Decide report={deciding} onClose={() => setDeciding(null)} />
    </section>
  )
}

function Decide({ report, onClose }: { report: Report | null; onClose: () => void }) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [action, setAction] = useState<Action>('dismiss')
  const [statement, setStatement] = useState('')
  const [busy, setBusy] = useState(false)
  const short = statement.trim().length < 20
  const submit = async () => {
    if (!report) return
    setBusy(true)
    try {
      await decideReport(report.id, action, statement.trim())
      toast(t('Decided. The people concerned have been told'))
      setStatement('')
      onClose()
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
      await qc.invalidateQueries({ queryKey: ['adminReports'] })
      await qc.invalidateQueries({ queryKey: ['audit'] })
    }
  }
  const actions: Action[] = report?.targetType === 'listing' ? ['dismiss', 'take_down', 'suspend'] : ['dismiss', 'suspend']
  return (
    <Sheet
      open={Boolean(report)}
      onClose={onClose}
      title={t('Decide on this report')}
      footer={
        <Button block size="lg" disabled={busy || short} onClick={() => void submit()}>
          {t(ACTION_LABEL[action])}
        </Button>
      }
    >
      <div className="space-y-4 pb-3">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('Decision')}>
          {actions.map((a) => (
            <Button key={a} size="sm" variant={a === action ? 'ink' : 'secondary'} aria-pressed={a === action} onClick={() => setAction(a)}>
              {t(ACTION_LABEL[a])}
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
      </div>
    </Sheet>
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
  const [busy, setBusy] = useState(false)
  const spec = DIRECT[kind]
  const ready = target.trim() && (!spec.needsWhy || statement.trim().length >= 20)
  const run = async () => {
    setBusy(true)
    const to = target.trim()
    const why = statement.trim()
    try {
      if (kind === 'take_down') await takeDownListing(to, why)
      else if (kind === 'suspend') await suspendOwner(to, why)
      else if (kind === 'reinstate') await reinstateOwner(to, why)
      else await resolveDispute(to, kind)
      toast(t('Done'))
      setTarget('')
      setStatement('')
    } catch (err) {
      toast(messageOf(err))
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
        <Button disabled={busy || !ready} onClick={() => void run()}>
          {t(spec.label)}
        </Button>
      </Card>
    </section>
  )
}

function Audit() {
  const audit = useAudit()
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
                <p className="text-[14.5px] font-semibold">
                  {a.action} · {a.targetType} <span className="tnum text-[var(--ink-3)]">{a.targetId}</span>
                </p>
                <p className="t-sm text-[var(--ink-4)]">
                  {t('by {who}', { who: a.actorId })} · {ago(a.at)}
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
