import { useEffect, useId, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { BookingStatus } from '../../domain/types.ts'
import { addEvidence, mediaUrl, uploadPhoto, useEvidence, type EvidenceStage } from '../../data/repo.ts'
import { shrink } from '../photos.ts'
import { messageOf, useMe, useToast } from '../store.tsx'
import { ago } from '../format.ts'
import { Button, Card, Field, Sheet, Textarea } from './ui.tsx'
import { plural, t } from '../../i18n.ts'
import { Icon } from './Icon.tsx'

// Mirrors booking/messages.py: when each kind of photo can be added.
const CAN: Record<EvidenceStage, BookingStatus[]> = {
  check_in: ['accepted', 'active'],
  check_out: ['active', 'completed', 'disputed'],
}
const LABELS: Record<EvidenceStage, string> = { check_in: 'Check-in photos', check_out: 'Check-out photos' }
const ADD: Record<EvidenceStage, string> = { check_in: 'Add check-in photos', check_out: 'Add check-out photos' }
const SAVED: Record<EvidenceStage, string> = { check_in: 'Check-in photos saved', check_out: 'Check-out photos saved' }
const LABEL = new Proxy(LABELS, { get: (o, k: EvidenceStage) => t(o[k]) })
const WHY: Record<EvidenceStage, string> = {
  check_in: 'Photograph it as it is handed over: every side, any marks, the meter or counter if it has one.',
  check_out: 'Photograph it as it is handed back, the same way. Together they settle any question about damage.',
}

/**
 * Hand-over evidence: what the thing looked like when it changed hands.
 * `prompt` opens the add sheet for a stage (after marking the hand-over or
 * hand-back); `onPromptClosed` clears it.
 */
export function EvidencePanel({
  bookingId,
  status,
  otherName,
  prompt,
  onPromptClosed,
}: {
  bookingId: string
  status: BookingStatus
  otherName: string
  prompt: EvidenceStage | null
  onPromptClosed: () => void
}) {
  const id = useId()
  const me = useMe()
  const qc = useQueryClient()
  const toast = useToast()
  const evidence = useEvidence(bookingId)
  const [stage, setStage] = useState<EvidenceStage | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files])
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const open = stage ?? prompt
  const stages = (Object.keys(CAN) as EvidenceStage[]).filter((s) => CAN[s].includes(status))
  const items = evidence.data ?? []
  if (stages.length === 0 && items.length === 0) return null

  const close = () => {
    setStage(null)
    setFiles([])
    setNote('')
    onPromptClosed()
  }
  const save = async () => {
    if (!open || files.length === 0) return
    setBusy(true)
    try {
      const urls = []
      for (const f of files) urls.push(await uploadPhoto(await shrink(f), f.name.replace(/\.\w+$/, '.jpg')))
      await addEvidence(bookingId, open, urls, note.trim())
      await qc.invalidateQueries({ queryKey: ['evidence', bookingId] })
      toast(t(SAVED[open]))
      close()
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="mt-3 p-5">
      <h2 className="t-label mb-1">{t('Hand-over photos')}</h2>
      <p className="t-sm mb-3 text-[var(--ink-3)]">
        {t('Photos you both take when it changes hands. Cappy looks at them first if anything goes wrong.')}
      </p>
      {items.length > 0 && (
        <ul className="mb-3 space-y-3">
          {items.map((e) => (
            <li key={e.id}>
              <p className="t-sm mb-1.5 text-[var(--ink-3)]">
                {LABEL[e.stage]} · {e.by === me ? t('you') : otherName} · {ago(e.at)}
              </p>
              <div className="flex flex-wrap gap-2">
                {e.photos.map((src) => (
                  <a key={src} href={mediaUrl(src)} target="_blank" rel="noreferrer">
                    <img
                      src={mediaUrl(src)}
                      alt={t('{what} by {who}', { what: LABEL[e.stage], who: e.by === me ? t('you') : otherName })}
                      className="h-[72px] w-[72px] rounded-[10px] object-cover"
                      loading="lazy"
                    />
                  </a>
                ))}
              </div>
              {e.note && <p className="t-sm mt-1.5 text-[var(--ink-2)]">{e.note}</p>}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        {stages.map((s) => (
          <Button key={s} variant="secondary" icon="camera" onClick={() => setStage(s)}>
            {t(ADD[s])}
          </Button>
        ))}
      </div>

      <Sheet
        open={Boolean(open)}
        onClose={close}
        title={open ? LABEL[open] : ''}
        footer={
          <div className="space-y-2">
            <Button block size="lg" disabled={busy || files.length === 0} onClick={() => void save()}>
              {busy ? t('Uploading…') : files.length ? plural(files.length, 'Save {n} photo', 'Save {n} photos') : t('Save photos')}
            </Button>
            <Button block variant="quiet" onClick={close}>
              {t('Not now')}
            </Button>
          </div>
        }
      >
        <div className="space-y-4 pb-3">
          {open && <p className="t-body text-[var(--ink-2)]">{t(WHY[open])}</p>}
          <Field label={t('Photos')} htmlFor={`${id}-files`} hint={t('Up to 12. Taken now works best.')}>
            {/* The browser's own picker says "Choose Files" in the browser's language:
                a translated button over a hidden input instead (V3-12). */}
            <input
              id={`${id}-files`}
              type="file"
              accept="image/*"
              capture="environment"
              multiple
              className="sr-only"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 12))}
            />
            <label
              htmlFor={`${id}-files`}
              className="inline-flex min-h-[48px] cursor-pointer items-center gap-2 rounded-[var(--radius-control)] border border-[var(--line-strong)] px-4 text-[14.5px] font-semibold hover:border-[var(--ink-4)] focus-within:outline"
            >
              <Icon name="camera" size={18} />
              {files.length ? t('Choose other photos') : t('Take or choose photos')}
            </label>
            {previews.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {previews.map((src) => (
                  <img key={src} src={src} alt="" className="h-[64px] w-[64px] rounded-[10px] object-cover" />
                ))}
              </div>
            )}
          </Field>
          <Field label={t('Note (optional)')} htmlFor={`${id}-note`}>
            <Textarea
              id={`${id}-note`}
              rows={2}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t('Scratch on the left side was already there')}
            />
          </Field>
        </div>
      </Sheet>
    </Card>
  )
}
