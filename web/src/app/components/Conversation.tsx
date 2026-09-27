import { Fragment, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, HIDDEN_CONTACT, markInboxRead, sendMessage, unblockPerson, useAttemptKey, useBlocks, useMessages, type Message } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { ago, dayShort } from '../format.ts'
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
          className="mx-0.5 inline-block rounded-[var(--radius-control)] bg-[var(--sunken)] px-1.5 text-label font-semibold text-[var(--ink-3)]"
        >
          {/* The server shows it again once the booking is accepted (V3-6); a booking
              that closed before that never reveals it. */}
          {closed ? t('contact hidden') : t('contact hidden until accepted')}
        </span>,
      )
  })
  return <p className="whitespace-pre-wrap break-words text-body leading-[1.375rem]">{out}</p>
}

function Bubble({ m, otherName, closed, last }: { m: Message; otherName: string; closed: boolean; last: boolean }) {
  return (
    <li className={`flex flex-col ${m.mine ? 'items-end' : 'items-start'} ${last ? '' : '-mb-2'}`}>
      <div
        // Messenger bubbles (VD-19): yours in ink on the right, theirs on the
        // paper tone on the left; the corner nearest the sender tucks in on
        // the last bubble of a run, the way iMessage and Vinted draw a tail.
        className={`max-w-[85%] rounded-[var(--radius-l)] px-4 py-2.5 ${
          m.mine
            ? `bg-[var(--inverse)] text-[var(--on-inverse)] ${last ? 'rounded-br-[var(--radius-xs)]' : ''}`
            : `bg-[var(--sunken)] text-[var(--ink)] ${last ? 'rounded-bl-[var(--radius-xs)]' : ''}`
        }`}
      >
        <Body text={m.body} closed={closed} />
      </div>
      {m.mine && m.flagged && (
        <p role="note" className="t-sm mt-1 max-w-[85%] text-right text-[var(--warn)]">
          {t('Keep payments on Cappy: money paid outside it is not protected, and asking for it breaks our rules.')}
        </p>
      )}
      {/* Who and when, once per run of messages rather than under each one.
          A div: the report button carries a sheet, which may not sit inside a <p> (V5-15). */}
      {last && (
        <div className="t-sm mt-1 flex items-center gap-1 px-1 text-[var(--ink-4)]">
          {m.mine ? t('You') : otherName} · {ago(m.at)}
          {!m.mine && (
            <ReportButton targetType="message" targetId={m.id} compact offerBlock={{ sub: m.senderId, name: otherName }} />
          )}
        </div>
      )}
    </li>
  )
}

/** Sets --kb to the height the on-screen keyboard covers, so sticky things sit above it. */
function useKeyboardInset() {
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const root = document.documentElement.style
    const set = () => root.setProperty('--kb', `${Math.max(0, innerHeight - vv.height - vv.offsetTop)}px`)
    vv.addEventListener('resize', set)
    vv.addEventListener('scroll', set)
    return () => {
      vv.removeEventListener('resize', set)
      vv.removeEventListener('scroll', set)
      root.removeProperty('--kb')
    }
  }, [])
}

/** Messages between the two sides of one booking. */
export function Conversation({
  bookingId,
  status,
  otherName,
  otherId,
  accepted,
  closed = false,
}: {
  bookingId: string
  /** The booking's status: a change reads the thread again (masking follows it, V5-5). */
  status?: string
  otherName: string
  /** Whom a block would stop: blocked either way, nothing more is sent (V7-5). */
  otherId?: string
  /** Before acceptance the server masks phone numbers, emails and links. */
  accepted: boolean
  /** Declined, cancelled, lapsed: the conversation stays readable, nothing more is sent. */
  closed?: boolean
}) {
  const id = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const messages = useMessages(bookingId, status)
  // Kept across a session expiring mid-sentence (U-10); one key per message (U-6).
  const [draft, setDraftState] = useState(() => drafts.get(`msg.${bookingId}`) ?? '')
  const setDraft = (v: string) => {
    setDraftState(v)
    drafts.set(`msg.${bookingId}`, v)
  }
  const attempt = useAttemptKey()
  const online = useOnline()
  const [busy, setBusy] = useState(false)
  // The server closes a conversation too (a completed booking past its review
  // window): its 409 closes the composer here, with the reason (FL, V4-18).
  const [closedHere, setClosedHere] = useState(false)
  closed = closed || closedHere
  const blocks = useBlocks()
  // Blocked by me (the list) or by them (the server refuses with 403).
  const [refusedHere, setRefusedHere] = useState(false)
  const iBlocked = Boolean(otherId && blocks.data?.includes(otherId))
  const blocked = iBlocked || refusedHere
  const list = useRef<HTMLUListElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  // Opened from the Inbox (#messages): bring the thread into view once it is there.
  const arrived = Boolean(messages.data)
  useEffect(() => {
    if (arrived && location.hash === '#messages') heading.current?.scrollIntoView({ block: 'start' })
  }, [arrived])
  const items = messages.data?.items ?? []

  // The newest message in view by scrolling the list itself, never the page:
  // scrollIntoView scrolled the whole booking page 477 px down on open (UX-25).
  useEffect(() => {
    const el = list.current
    if (el) el.scrollTop = el.scrollHeight
    // Read here: the server's receipt drops the Inbox's dot on every device (UX-12).
    const last = items[items.length - 1]
    if (last && !last.mine) void markInboxRead(bookingId).then(() => qc.invalidateQueries({ queryKey: ['inbox'] }), () => undefined)
  }, [items.length, bookingId])

  useKeyboardInset()

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
      if (err instanceof ApiError && err.code === 'conversation_closed') setClosedHere(true)
      else if (err instanceof ApiError && err.status === 403) setRefusedHere(true)
      else toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="mt-3 p-5">
      <h2 ref={heading} id="messages" className="t-label mb-1 scroll-mt-24">{t('Messages with {name}', { name: otherName })}</h2>
      {items.some((m) => !m.mine && m.flagged) && (
        <p role="note" className="t-sm mb-3 rounded-[var(--radius-control)] bg-[var(--warn-subtle)] p-3 text-[var(--ink-2)]">
          {t('{name} asked about paying outside Cappy. Payments outside Cappy are not protected: no refund, no help if something goes wrong. Report the message if it happens again.', { name: otherName })}
        </p>
      )}
      {!accepted && !closed && (
        <p className="t-sm mb-3 text-[var(--ink-3)]">
          {t('Phone numbers, emails and links stay hidden until the booking is accepted. Keep payments in Cappy, so you are both protected.')}
        </p>
      )}
      {items.length === 0 ? (
        // No invitation to write on a booking nobody can write on (V4-18).
        closed || blocked ? null : (
          <p className="t-sm py-3 text-[var(--ink-3)]">{t('No messages yet. Say hello, and ask about the hand-over or anything else.')}</p>
        )
      ) : (
        <ul ref={list} className="max-h-[360px] space-y-3 overflow-y-auto overscroll-contain py-2" aria-live="polite">
          {items.map((m, i) => {
            // A quiet day line where the day changes (iMessage, WhatsApp); a run ends there too.
            const d = dayShort(m.at)
            const next = items[i + 1]
            return (
              <Fragment key={m.id}>
                {(i === 0 || dayShort(items[i - 1].at) !== d) && (
                  <li role="separator" className="t-sm py-1 text-center font-medium text-[var(--ink-4)]">{d}</li>
                )}
                <Bubble m={m} otherName={otherName} closed={closed} last={next?.mine !== m.mine || dayShort(next.at) !== d} />
              </Fragment>
            )
          })}
        </ul>
      )}
      {closed ? (
        <p className="t-sm mt-3 text-[var(--ink-3)]">{t('This booking is closed, so no new messages can be sent.')}</p>
      ) : blocked ? (
        <p className="t-sm mt-3 flex flex-wrap items-center gap-x-3 text-[var(--ink-3)]">
          {iBlocked
            ? t('You blocked {name}, so no messages can be sent.', { name: otherName })
            : t('Messages to {name} cannot be sent.', { name: otherName })}
          {iBlocked && otherId && (
            <button
              type="button"
              className="font-semibold text-[var(--ink)] underline"
              onClick={async () => {
                try {
                  await unblockPerson(otherId)
                  toast(t('Unblocked'))
                } catch (err) {
                  toast(messageOf(err), 'error')
                } finally {
                  await qc.invalidateQueries({ queryKey: ['blocks'] })
                }
              }}
            >
              {t('Unblock')}
            </button>
          )}
        </p>
      ) : (
        <>
        {!draft && (
          // Quick replies (Airbnb, Vinted): the three things people write most,
          // one tap to start a message, still editable before sending.
          <div className="rail mt-3 pb-1" aria-label={t('Suggested messages')}>
            {[t('Hi! Is everything set for the booking?'), t('How does the hand-over work?'), t('Thanks, see you then!')].map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => setDraft(q)}
                className="min-h-[44px] shrink-0 rounded-full border border-[var(--line-strong)] px-4 py-2 text-label font-medium text-[var(--ink-2)] transition-colors duration-[var(--dur-short)] hover:bg-[var(--sunken)]"
              >
                {q}
              </button>
            ))}
          </div>
        )}
        <form
          // Stays in reach while the thread is long, and above the on-screen
          // keyboard: --kb is the part of the layout viewport it covers.
          className="sticky bottom-[max(var(--kb,0px),calc(var(--dock-h)+var(--footer-h,0px)+16px))] z-10 -mx-5 mt-3 flex items-end gap-2 bg-[var(--surface)] px-5 py-2"
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
        </>
      )}
    </Card>
  )
}
