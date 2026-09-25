import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HIDDEN_CONTACT, sendMessage, useMessages, type Message } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { ago } from '../format.ts'
import { Button, Card, Textarea } from './ui.tsx'
import { ReportButton } from './Report.tsx'
import { t } from '../../i18n.ts'

/** Contact details the server hid before the booking was accepted, shown as a quiet chip. */
function Body({ text }: { text: string }) {
  const parts = text.split(HIDDEN_CONTACT)
  const out: ReactNode[] = []
  parts.forEach((part, i) => {
    out.push(part)
    if (i < parts.length - 1)
      out.push(
        <span
          key={i}
          className="mx-0.5 inline-block rounded-[var(--radius-control)] bg-[var(--sunken)] px-1.5 text-[12.5px] font-semibold text-[var(--ink-3)]"
        >
          {t('contact hidden until accepted')}
        </span>,
      )
  })
  return <p className="whitespace-pre-wrap break-words text-[15px] leading-[22px]">{out}</p>
}

function Bubble({ m, otherName }: { m: Message; otherName: string }) {
  return (
    <li className={`flex flex-col ${m.mine ? 'items-end' : 'items-start'}`}>
      <div
        className={`max-w-[85%] rounded-[14px] px-3.5 py-2.5 ${
          m.mine ? 'bg-[var(--field)] text-[var(--on-field)]' : 'bg-[var(--sunken)] text-[var(--ink)]'
        }`}
      >
        <Body text={m.body} />
      </div>
      <p className="t-sm mt-1 flex items-center gap-1 text-[var(--ink-4)]">
        {m.mine ? t('You') : otherName} · {ago(m.at)}
        {!m.mine && <ReportButton targetType="message" targetId={m.id} compact />}
      </p>
    </li>
  )
}

/** Messages between the two sides of one booking. */
export function Conversation({
  bookingId,
  otherName,
  accepted,
}: {
  bookingId: string
  otherName: string
  /** Before acceptance the server masks phone numbers, emails and links. */
  accepted: boolean
}) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const messages = useMessages(bookingId)
  const [draft, setDraft] = useState('')
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
      await sendMessage(bookingId, text)
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
      {!accepted && (
        <p className="t-sm mb-3 text-[var(--ink-3)]">
          {t('Phone numbers, emails and links are hidden until the booking is accepted. Keep payments on Cappy: that is what protects you both.')}
        </p>
      )}
      {items.length === 0 ? (
        <p className="t-sm py-3 text-[var(--ink-3)]">{t('No messages yet. Ask about the hand-over, access or anything you need.')}</p>
      ) : (
        <ul className="max-h-[360px] space-y-3 overflow-y-auto py-2" aria-live="polite">
          {items.map((m) => (
            <Bubble key={m.id} m={m} otherName={otherName} />
          ))}
          <div ref={end} />
        </ul>
      )}
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
        <Button type="submit" disabled={busy || !draft.trim()}>
          {t('Send')}
        </Button>
      </form>
    </Card>
  )
}
