import { useId, useState } from 'react'
import { useSession } from '../../data/auth.ts'
import { useQueryClient } from '@tanstack/react-query'
import { REPORT_REASONS, blockPerson, sendReport, useAttemptKey, useMarket, type ReportReason, type ReportTarget } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { Button, Check, Field, Input, Select, Sheet, Textarea } from './ui.tsx'
import { t } from '../../i18n.ts'

const KIND: Record<ReportTarget, string> = {
  listing: 'A listing',
  owner: 'A profile',
  message: 'A message',
  review: 'A review',
}

/** The id in a pasted link (`…/listing/l9?x` → `l9`) or the reference itself. */
export function referenceId(raw: string): string {
  const s = raw.trim()
  if (!s) return ''
  try {
    const path = new URL(s, 'https://x.invalid').pathname.replace(/\/+$/, '')
    return decodeURIComponent(path.split('/').pop() ?? '').slice(0, 100)
  } catch {
    return s.slice(0, 100)
  }
}

const TITLE: Record<ReportTarget, string> = {
  listing: 'Report this listing',
  owner: 'Report this person',
  message: 'Report this message',
  review: 'Report this review',
}

/**
 * "Report": a notice to Cappy about content (DSA Art. 16). Anyone can send
 * one; without an account they leave an email so we can say what we decided.
 */
export function ReportButton({
  targetType: fixedType,
  targetId: fixedId,
  className = '',
  compact = false,
  offerBlock,
}: {
  /** Absent on the public reporting page (FL-10): the reporter says what and
   *  pastes a link or reference instead. */
  targetType?: ReportTarget
  targetId?: string
  className?: string
  compact?: boolean
  /** Who sent it: after the report, blocking them is one tap (U-13). */
  offerBlock?: { sub: string; name: string }
}) {
  const qc = useQueryClient()
  const session = useSession()
  const emergency = useMarket().emergencyNumber
  const toast = useToast()
  const id = useId()
  const [open, setOpen] = useState(false)
  // No reason chosen for them: a preselected "fraud" became the reason of many reports (V5-32).
  const [reason, setReason] = useState<ReportReason | ''>('')
  const [details, setDetails] = useState('')
  const [email, setEmail] = useState('')
  const [goodFaith, setGoodFaith] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<string | null>(null)
  const attempt = useAttemptKey()
  const [freeType, setFreeType] = useState<ReportTarget>('listing')
  const [reference, setReference] = useState('')
  const free = !fixedType || !fixedId
  const targetType = fixedType ?? freeType
  const targetId = fixedId ?? referenceId(reference)
  const noTarget = free && !targetId

  const tooShort = details.trim().length < 10
  const needsEmail = !session && !/^\S+@\S+\.\S+$/.test(email.trim())

  const submit = async () => {
    setBusy(true)
    try {
      const report = {
        targetType,
        targetId,
        reason: reason as ReportReason,
        details: details.trim(),
        email: session ? undefined : email.trim(),
        goodFaith: true as const,
      }
      const r = await sendReport(report, attempt.keyFor(report))
      attempt.settle()
      setSent(r.id)
    } catch (err) {
      attempt.settle(err)
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  const close = () => {
    setOpen(false)
    setSent(null)
    setDetails('')
  }

  return (
    <>
      <Button
        variant={free ? 'secondary' : 'quiet'}
        size={compact ? 'sm' : 'md'}
        icon="alert"
        className={className}
        onClick={() => setOpen(true)}
        aria-label={free ? t('Report content') : t(TITLE[targetType])}
      >
        {compact ? null : free ? t('Report content') : t('Report')}
      </Button>
      <Sheet
        open={open}
        onClose={close}
        title={sent ? t('Thank you') : free ? t('Report content') : t(TITLE[targetType])}
        footer={
          sent ? (
            <div className="space-y-2">
              {offerBlock && session && (
                <Button
                  block
                  size="lg"
                  variant="danger"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      await blockPerson(offerBlock.sub)
                      await qc.invalidateQueries({ queryKey: ['blocks'] })
                      toast(t('{name} is blocked', { name: offerBlock.name }))
                      close()
                    } catch (err) {
                      toast(messageOf(err), 'error')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {t('Block {name} too', { name: offerBlock.name })}
                </Button>
              )}
              <Button block size="lg" variant={offerBlock && session ? 'quiet' : 'primary'} onClick={close}>
                {t('Done')}
              </Button>
            </div>
          ) : (
            <Button block size="lg" disabled={busy || !reason || tooShort || needsEmail || !goodFaith || noTarget} onClick={() => void submit()}>
              {t('Send report')}
            </Button>
          )
        }
      >
        {sent ? (
          <p className="t-body pb-3 text-[var(--ink-2)]" role="status">
            {t('We have your report and will tell you what we decide. Your reference is')}{' '}
            <span className="tnum font-semibold text-[var(--ink)]">{sent}</span>.
          </p>
        ) : (
          <div className="space-y-4 pb-3">
            {free && (
              <>
                <Field label={t('What are you reporting?')} htmlFor={`${id}-type`}>
                  <Select id={`${id}-type`} value={freeType} onChange={(e) => setFreeType(e.target.value as ReportTarget)}>
                    {(Object.keys(KIND) as ReportTarget[]).map((k) => (
                      <option key={k} value={k}>
                        {t(KIND[k])}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label={t('Link or reference')}
                  htmlFor={`${id}-ref`}
                  hint={t('Paste the link to it, or the reference shown on it.')}
                >
                  <Input id={`${id}-ref`} value={reference} onChange={(e) => setReference(e.target.value)} />
                </Field>
              </>
            )}
            <Field label={t('What is wrong?')} htmlFor={`${id}-reason`}>
              <Select id={`${id}-reason`} value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
                <option value="" disabled>
                  {t('Choose a reason')}
                </option>
                {REPORT_REASONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label={t('Tell us more')}
              htmlFor={`${id}-details`}
              hint={t('Where exactly, and why. At least 10 characters.')}
            >
              <Textarea
                id={`${id}-details`}
                rows={4}
                maxLength={2000}
                value={details}
                onChange={(e) => setDetails(e.target.value)}
              />
            </Field>
            {!session && (
              <Field label={t('Your email')} htmlFor={`${id}-email`} hint={t('So we can tell you what we decide.')}>
                <Input
                  id={`${id}-email`}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
            )}
            {/* DSA Art. 16(2)(d): the notice carries the reporter's statement of good faith. */}
            <Check
              checked={goodFaith}
              onChange={setGoodFaith}
              label={t('I confirm this report is accurate and complete to the best of my knowledge.')}
            />
            <p className="t-sm text-[var(--ink-3)]">
              {t('If someone is in danger, call {number} first. Reports are read by people at Cappy.', { number: emergency })}
            </p>
          </div>
        )}
      </Sheet>
    </>
  )
}

/** "Block": no messages and no new bookings between the two of you. */
export function BlockButton({ sub, name }: { sub: string; name: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const block = async () => {
    setBusy(true)
    try {
      await blockPerson(sub)
      await qc.invalidateQueries({ queryKey: ['blocks'] })
      toast(t('{name} is blocked', { name }))
      setOpen(false)
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button variant="quiet" icon="close" onClick={() => setOpen(true)}>
        {t('Block')}
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t('Block {name}?', { name })}
        footer={
          <Button block size="lg" variant="danger" disabled={busy} onClick={() => void block()}>
            {t('Block {name}', { name })}
          </Button>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {t('Neither of you will be able to message the other or make new bookings with each other. Bookings you already have stay as they are. You can unblock {name} from your profile. If something is wrong, report them too, so Cappy can act.', { name })}
        </p>
      </Sheet>
    </>
  )
}
