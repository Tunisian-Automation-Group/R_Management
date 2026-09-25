import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HIDDEN_CONTACT, sendMessage, useAttemptKey, useMessages, type Message } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { ago } from '../format.ts'
import { Button, Card, Textarea } from './ui.tsx'
import { ReportButton } from './Report.tsx'
import { t } from '../../i18n.ts'
import { drafts } from '../device.ts'
import { useOnline } from './Offline.tsx'

/** Contact details the server hid before the booking was accepted, shown as a quiet chip. */
function Body({ text, closed }: { text: string; closed: boolean }) {
  const parts = text.split(HIDDEN_CONTACT)
  const out: ReactNode[] = []
  parts.forEach((part, i) => {
    out.push(part)
    if (i < parts.length - 1)
      out.push(
        <span
          key={i}
          className="mx-0.5 inline-block rounded-[var(--radius-control)] bg-[var(--sunken)] px-1.5 text-[0.7812rem] font-semibold text-[var(--ink-3)]"
        >
          {/* The server shows it again once the booking is accepted (V3-6); a booking
              that closed before that never reveals it. */}
          {closed ? t('contact hidden') : t('contact hidden until accepted')}
        </span>,
      )
  })
  return <p className="whitespace-pre-wrap break-words text-[0.9375rem] leading-[1.375rem]">{out}</p>
}

function Bubble({ m, otherName, closed }: { m: Message; otherName: string; closed: boolean }) {
  return (
    <li className={`flex flex-col ${m.mine ? 'items-end' : 'items-start'}`}>
      <div
        className={`max-w-[85%] rounded-[14px] px-3.5 py-2.5 ${
          m.mine ? 'bg-[var(--field)] text-[var(--on-field)]' : 'bg-[var(--sunken)] text-[var(--ink)]'
        }`}
      >
        <Body text={m.body} closed={closed} />
      </div>
      {m.mine && m.flagged && (
        <p role="note" className="t-sm mt-1 max-w-[85%] text-right text-[var(--warn)]">
          {t('Keep payments on Cappy: money paid outside it is not protected, and asking for it breaks our rules.')}
        </p>
      )}
      <p className="t-sm mt-1 flex items-center gap-1 text-[var(--ink-4)]">
        {m.mine ? t('You') : otherName} · {ago(m.at)}
        {!m.mine && (
          <ReportButton targetType="message" targetId={m.id} compact offerBlock={{ sub: m.senderId, name: otherName }} />
        )}
      </p>
    </li>
  )
}

/** Messages between the two sides of one booking. */
export function Conversation({
  bookingId,
  otherName,
  accepted,
  closed = false,
}: {
  bookingId: string
  otherName: string
  /** Before acceptance the server masks phone numbers, emails and links. */
  accepted: boolean
  /** Declined, cancelled, lapsed: the conversation stays readable, nothing more is sent. */
  closed?: boolean
}) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const messages = useMessages(bookingId)
  // Kept across a session expiring mid-sentence (U-10); one key per message (U-6).
  const [draft, setDraftState] = useState(() => drafts.get(`msg.${bookingId}`) ?? '')
  const setDraft = (v: string) => {
    setDraftState(v)
    drafts.set(`msg.${bookingId}`, v)
  }
  const attempt = useAttemptKey()
  const online = useOnline()
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const items = messages.data?.items ?? []

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [items.length])

  const send = async () => {
    const text = draft.trim()
    if (!text) return
    setBusy(true)
    try {
      try {
        await sendMessage(bookingId, text, attempt.keyFor(text))
      } catch (err) {
        attempt.settle(err)
        throw err
      }
      attempt.settle()
      setDraft('')
      await qc.invalidateQueries({ queryKey: ['messages', bookingId] })
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="mt-3 p-5">
      <h2 className="t-label mb-1">{t('Messages with {name}', { name: otherName })}</h2>
      {items.some((m) => !m.mine && m.flagged) && (
        <p role="note" className="t-sm mb-3 rounded-[var(--radius-control)] bg-[var(--warn-subtle)] p-3 text-[var(--ink-2)]">
          {t('{name} asked about paying outside Cappy. Payments outside Cappy are not protected: no refund, no help if something goes wrong. Report the message if it happens again.', { name: otherName })}
        </p>
      )}
      {!accepted && !closed && (
        <p className="t-sm mb-3 text-[var(--ink-3)]">
          {t('Phone numbers, emails and links are hidden until the booking is accepted, then shown. Keep payments on Cappy: that is what protects you both.')}
        </p>
      )}
      {items.length === 0 ? (
        <p className="t-sm py-3 text-[var(--ink-3)]">{t('No messages yet. Ask about the hand-over, access or anything you need.')}</p>
      ) : (
        <ul className="max-h-[360px] space-y-3 overflow-y-auto py-2" aria-live="polite">
          {items.map((m) => (
            <Bubble key={m.id} m={m} otherName={otherName} closed={closed} />
          ))}
          <div ref={end} />
        </ul>
      )}
      {closed ? (
        <p className="t-sm mt-3 text-[var(--ink-3)]">{t('This booking is closed, so no new messages can be sent.')}</p>
      ) : (
        <form
          className="mt-3 flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void send()
          }}
        >
          <label htmlFor={`${id}-msg`} className="sr-only">
            {t('Message to {name}', { name: otherName })}
          </label>
          <Textarea
            id={`${id}-msg`}
            rows={2}
            maxLength={2000}
            value={draft}
            placeholder={t('Write to {name}', { name: otherName })}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void send()
            }}
          />
          <Button type="submit" disabled={busy || !draft.trim() || !online}>
            {t('Send')}
          </Button>
        </form>
      )}
    </Card>
  )
}
