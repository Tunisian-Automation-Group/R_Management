import { useId, useState } from 'react'
import { useSession } from '../../data/auth.ts'
import { useQueryClient } from '@tanstack/react-query'
import { REPORT_REASONS, blockPerson, sendReport, type ReportReason, type ReportTarget } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { Button, Field, Input, Select, Sheet, Textarea } from './ui.tsx'

const WHAT: Record<ReportTarget, string> = {
  listing: 'this listing',
  owner: 'this person',
  message: 'this message',
  review: 'this review',
}

/**
 * "Report": a notice to Cappy about content (DSA Art. 16). Anyone can send
 * one; without an account they leave an email so we can say what we decided.
 */
export function ReportButton({
  targetType,
  targetId,
  className = '',
  compact = false,
}: {
  targetType: ReportTarget
  targetId: string
  className?: string
  compact?: boolean
}) {
  const session = useSession()
  const toast = useToast()
  const id = useId()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<ReportReason>('fraud')
  const [details, setDetails] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<string | null>(null)

  const tooShort = details.trim().length < 10
  const needsEmail = !session && !/^\S+@\S+\.\S+$/.test(email.trim())

  const submit = async () => {
    setBusy(true)
    try {
      const r = await sendReport({
        targetType,
        targetId,
        reason,
        details: details.trim(),
        email: session ? undefined : email.trim(),
      })
      setSent(r.id)
    } catch (err) {
      toast(messageOf(err))
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
        variant="quiet"
        size={compact ? 'sm' : 'md'}
        icon="alert"
        className={className}
        onClick={() => setOpen(true)}
        aria-label={`Report ${WHAT[targetType]}`}
      >
        {compact ? null : 'Report'}
      </Button>
      <Sheet
        open={open}
        onClose={close}
        title={sent ? 'Thank you' : `Report ${WHAT[targetType]}`}
        footer={
          sent ? (
            <Button block size="lg" onClick={close}>
              Done
            </Button>
          ) : (
            <Button block size="lg" disabled={busy || tooShort || needsEmail} onClick={() => void submit()}>
              Send report
            </Button>
          )
        }
      >
        {sent ? (
          <p className="t-body pb-3 text-[var(--ink-2)]" role="status">
            We have your report and will tell you what we decide. Your reference is{' '}
            <span className="tnum font-semibold text-[var(--ink)]">{sent}</span>.
          </p>
        ) : (
          <div className="space-y-4 pb-3">
            <Field label="What is wrong?" htmlFor={`${id}-reason`}>
              <Select id={`${id}-reason`} value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
                {REPORT_REASONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Tell us more"
              htmlFor={`${id}-details`}
              hint="Where exactly, and why. At least 10 characters."
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
              <Field label="Your email" htmlFor={`${id}-email`} hint="So we can tell you what we decide.">
                <Input
                  id={`${id}-email`}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
            )}
            <p className="t-sm text-[var(--ink-3)]">
              If someone is in danger, call 112 first. Reports are read by people at Cappy.
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
      toast(`${name} is blocked`)
      setOpen(false)
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button variant="quiet" icon="close" onClick={() => setOpen(true)}>
        Block
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={`Block ${name}?`}
        footer={
          <Button block size="lg" variant="danger" disabled={busy} onClick={() => void block()}>
            Block {name}
          </Button>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          Neither of you will be able to message the other or make new bookings with each other. Bookings you
          already have stay as they are. You can unblock {name} from your profile. If something is wrong, report
          them too, so Cappy can act.
        </p>
      </Sheet>
    </>
  )
}
