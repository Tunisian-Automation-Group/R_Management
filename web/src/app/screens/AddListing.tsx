import { useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type { CategoryId, Material, Slot } from '../../domain/types.ts'
import { CATEGORIES, category } from '../../domain/categories.ts'
import { formatEur } from '../../domain/money.ts'
import { messageOf, useCappy, useToast } from '../store.tsx'
import { useSession } from '../../data/auth.ts'
import { useQueryClient } from '@tanstack/react-query'
import * as repo from '../../data/repo.ts'
import { MAX_PHOTOS, shrink } from '../photos.ts'
import { Screen } from '../components/AppShell.tsx'
import { Icon, categoryIcon } from '../components/Icon.tsx'
import {
  Banner,
  Button,
  Card,
  Chip,
  Field,
  Input,
  MoneyInput,
  Textarea,
} from '../components/ui.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { NotFound } from './NotFound.tsx'
import { range } from '../format.ts'
import { lang, locale, plural, t } from '../../i18n.ts'

const MATERIALS: Material[] = [
  'PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'Resin',
  'Aluminium 6061', 'Stainless 304', 'Steel S235', 'Brass', 'POM', 'Acrylic', 'Plywood',
]

// Examples that match what is being listed (a 3D printer is not a Haas mill),
// and a starting price in cents per hour.
const EXAMPLES: Partial<Record<CategoryId, { title: string; blurb: string; machine?: string; rate: number }>> = {
  fabrication: { title: 'Haas VF-2SS', blurb: '3-axis, fast spindle, free most of August.', machine: 'Haas VF-2SS', rate: 6000 },
  additive: { title: 'Bambu Lab X1 Carbon', blurb: 'Multi-colour, enclosed, free most nights.', machine: 'Bambu Lab X1 Carbon', rate: 800 },
  finishing: { title: 'Powder-coating booth', blurb: 'RAL colours in stock, cured the same day.', machine: 'Powder-coating line', rate: 4500 },
  print: { title: 'Roland large-format printer', blurb: 'Banners up to 1.6 m wide.', machine: 'Roland TrueVIS VG3', rate: 3500 },
  freight: { title: '7.5 t box truck with driver', blurb: 'Tail lift, Berlin to anywhere in the EU.', machine: 'MAN TGL 7.5 t', rate: 5500 },
}
const DEFAULT_EXAMPLE: { title: string; blurb: string; machine?: string; rate: number } = {
  title: 'Festool TS 55 plunge saw',
  blurb: '8 kg, quiet, free most evenings.',
  rate: 400,
}
// Materials make sense where parts are made.
const TAKES_MATERIALS: CategoryId[] = ['fabrication', 'additive']

/** "List your 3D printing", "List your event & AV": lowercase unless it starts an acronym. */
function listYour(label: string): string {
  // German nouns keep their capital.
  if (lang() === 'de') return label
  return /^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label
}

const RULE_SUGGESTIONS = [
  'Back the same day',
  'Leave it as you found it',
  'No smoking',
  'Message me before you arrive',
  'Not for commercial use',
]

type Availability = 'evenings' | 'workday' | 'weekend' | 'always' | 'custom'

const AVAILABILITY: { id: Availability; label: string; detail: string; from: number; to: number; days: number[] }[] = [
  { id: 'evenings', label: 'Evenings', detail: '18:00 – 23:00, every day', from: 18, to: 23, days: [0, 1, 2, 3, 4, 5, 6] },
  { id: 'workday', label: 'While I am at work', detail: '09:00 – 18:00, Mon to Fri', from: 9, to: 18, days: [0, 1, 2, 3, 4] },
  { id: 'weekend', label: 'Weekends', detail: '09:00 – 20:00, Sat and Sun', from: 9, to: 20, days: [5, 6] },
  { id: 'always', label: 'Most of the time', detail: '07:00 – 22:00, every day', from: 7, to: 22, days: [0, 1, 2, 3, 4, 5, 6] },
]

/**
 * The presets cover most idle time, but a mill free from the 3rd to the 14th
 * or a van going on Thursday is a date range, not a habit. "Pick the dates
 * myself" takes a first day, a last day and the hours on each of those days.
 */
type CustomWindow = { from: string; until: string; start: string; end: string }

const weekday = (d: Date) => d.toLocaleDateString(locale(), { weekday: 'short' })

/** Longest range the form accepts. Beyond a quarter, nobody knows their idle time. */
const MAX_CUSTOM_DAYS = 92

/** "2026-09-25" as local midnight, or null when the input is empty or nonsense. */
function parseDay(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d
}

/** "18:30" as hours since midnight, or null. */
function parseClock(value: string): number | null {
  const m = /^(\d{2}):(\d{2})$/.exec(value)
  if (!m) return null
  const h = Number(m[1]) + Number(m[2]) / 60
  return h >= 0 && h < 24 ? h : null
}

const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

const shortDate = (d: Date) => d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' })

function defaultCustom(): CustomWindow {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const until = new Date(today.getTime() + 13 * 86_400_000)
  return { from: isoDay(today), until: isoDay(until), start: '18:00', end: '22:00' }
}

/** Why a custom window cannot be used yet, or null when it can. */
function customProblem(c: CustomWindow): string | null {
  const from = parseDay(c.from)
  const until = parseDay(c.until)
  const start = parseClock(c.start)
  const end = parseClock(c.end)
  if (!from || !until) return t('Pick a first and a last day.')
  if (until < from) return t('The last day comes before the first.')
  if ((until.getTime() - from.getTime()) / 86_400_000 > MAX_CUSTOM_DAYS) {
    return t('Keep it under {n} days. You can add more later.', { n: MAX_CUSTOM_DAYS })
  }
  if (start === null || end === null) return t('Pick the hours it is free on those days.')
  if (end <= start) return t('It has to stop being free after it starts being free.')
  if (end - start < 0.5) return t('Give people at least half an hour.')
  return null
}

/** Days in the range, both ends included. Only meaningful once it validates. */
function customDayCount(c: CustomWindow): number {
  const from = parseDay(c.from)!
  const until = parseDay(c.until)!
  return Math.round((until.getTime() - from.getTime()) / 86_400_000) + 1
}

/** "25 Sep – 8 Oct, 18:00 – 22:00", or the problem with it. */
function customSummary(c: CustomWindow): string {
  const problem = customProblem(c)
  if (problem) return problem
  const from = parseDay(c.from)!
  const until = parseDay(c.until)!
  const days = from.getTime() === until.getTime() ? shortDate(from) : `${shortDate(from)} – ${shortDate(until)}`
  return `${days}, ${c.start} – ${c.end}`
}

type Errors = Partial<
  Record<'title' | 'blurb' | 'rate' | 'instructions' | 'machine' | 'availability' | 'photos' | 'address', string>
>

/** A photograph on its way in: shown at once from the file, sent shrunk, and
 *  carrying the server's URL once it has one. The first in the list is the cover. */
type PhotoDraft = { key: string; preview: string; url?: string; error?: string }

/** New listing at /earn/new; editing one of yours at /earn/edit/:id. */
export function AddListing() {
  const { id } = useParams()
  const session = useSession()
  const mine = repo.useMyListings()
  if (!session) return <Navigate to={`/login?next=${encodeURIComponent(id ? `/earn/edit/${id}` : '/earn/new')}`} replace />
  if (!id) return <ListingForm />
  if (mine.isPending) return <Screen back="/earn">{null}</Screen>
  const view = mine.data?.items.find((v) => v.listing.id === id)
  if (!view) return <NotFound what="listing" />
  return <ListingForm key={id} edit={view} />
}

function ListingForm({ edit }: { edit?: repo.ListingView }) {
  const nav = useNavigate()
  const { state } = useCappy()
  const toast = useToast()
  const qc = useQueryClient()
  const districts = repo.useDistricts()
  const [saving, setSaving] = useState(false)
  const was = edit?.listing
  const wasWindow = was?.mode === 'window' ? was : undefined
  const wasBatch = was?.mode === 'batch' ? was : undefined

  const [categoryId, setCategoryId] = useState<CategoryId | null>(was?.category ?? null)
  const [title, setTitle] = useState(was?.title ?? '')
  const [blurb, setBlurb] = useState(was?.blurb ?? '')
  const [district, setDistrict] = useState(was?.district ?? (state.search.district || 'Kreuzberg'))
  const [address, setAddress] = useState(edit?.address ?? '')
  const [rate, setRate] = useState(was?.ratePerHour ?? 400)
  const [extraFee, setExtraFee] = useState(wasWindow?.extraFee ?? 0)
  const [extraLabel, setExtraLabel] = useState(wasWindow && wasWindow.extraFee > 0 ? wasWindow.extraLabel : t('Consumables'))
  const [minHours, setMinHours] = useState(wasWindow?.minHours ?? 1)
  const [maxHours, setMaxHours] = useState(wasWindow?.maxHours ?? 6)
  const [machine, setMachine] = useState(wasBatch?.machine ?? '')
  const [materials, setMaterials] = useState<Material[]>(wasBatch?.materials ?? [])
  const [unitsPerHour, setUnitsPerHour] = useState(wasBatch?.unitsPerHour ?? 10)
  const [setupFee, setSetupFee] = useState(wasBatch?.setupFee ?? 1500)
  const [setupHours, setSetupHours] = useState(wasBatch?.setupHours ?? 1)
  const [dims, setDims] = useState(wasBatch?.maxDims ?? { x: 300, y: 300, z: 300 })
  // Editing: the windows already listed stay unless removed; new ones are optional.
  const [availability, setAvailability] = useState<Availability | 'none'>(edit ? 'none' : 'evenings')
  const [custom, setCustom] = useState<CustomWindow>(defaultCustom)
  const [keptSlots, setKeptSlots] = useState<Slot[]>(edit?.slots ?? [])
  const [instructions, setInstructions] = useState(was?.instructions ?? '')
  const [rules, setRules] = useState<string[]>(was?.rules.filter((r) => r !== 'Cash or bank transfer') ?? [])
  const [photos, setPhotos] = useState<PhotoDraft[]>(
    (was?.photos ?? []).map((url, i) => ({ key: `was-${i}`, preview: repo.mediaUrl(url), url })),
  )
  const fileInput = useRef<HTMLInputElement>(null)
  const [errors, setErrors] = useState<Errors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const meta = categoryId ? category(categoryId) : null
  const isBatch = meta?.mode === 'batch'
  const example = (categoryId && EXAMPLES[categoryId]) || DEFAULT_EXAMPLE

  // Validation runs on blur and on submit, never on every keystroke, which
  // shouts at people while they are still typing the first word.
  const validate = (): Errors => {
    const e: Errors = {}
    if (title.trim().length < 3) e.title = t('Give it a name people will recognise.')
    if (blurb.trim().length < 10) e.blurb = t('One line on condition or what it is good for.')
    if (rate <= 0) e.rate = t('Set a price above zero.')
    if (instructions.trim().length < 10) {
      e.instructions = t('Say how someone actually gets hold of it.')
    }
    if (address.trim().length < 5) e.address = t('The street address where it is collected or used.')
    if (isBatch && machine.trim().length < 2) e.machine = t('Which machine is it?')
    if (photos.some((p) => !p.url && !p.error)) e.photos = t('Give the photos a moment to finish uploading.')
    if (availability === 'custom') {
      const problem = customProblem(custom)
      if (problem) e.availability = problem
    }
    return e
  }

  const blur = (key: keyof Errors) => () => {
    setTouched((t) => ({ ...t, [key]: true }))
    setErrors((prev) => ({ ...prev, [key]: validate()[key] }))
  }

  const errorFor = (key: keyof Errors) => (touched[key] ? errors[key] : undefined)

  /** Show each picture straight away, then send it shrunk. Failures stay in
   *  the grid with the reason, so the person can remove them or try again. */
  const addPhotos = async (files: FileList | null) => {
    if (!files) return
    const picked = Array.from(files).slice(0, Math.max(0, MAX_PHOTOS - photos.length))
    const drafts: PhotoDraft[] = picked.map((f, i) => ({
      key: `${Date.now().toString(36)}-${i}-${f.name}`,
      preview: URL.createObjectURL(f),
    }))
    setPhotos((prev) => [...prev, ...drafts])
    setTouched((t) => ({ ...t, photos: true }))
    await Promise.all(
      picked.map(async (file, i) => {
        const key = drafts[i].key
        try {
          const url = await repo.uploadPhoto(await shrink(file), file.name.replace(/\.[^.]*$/, '') + '.jpg')
          setPhotos((prev) => prev.map((d) => (d.key === key ? { ...d, url } : d)))
        } catch (err) {
          const error = err instanceof Error ? err.message : t('Upload failed')
          setPhotos((prev) => prev.map((d) => (d.key === key ? { ...d, error } : d)))
        }
      }),
    )
    setErrors((prev) => ({ ...prev, photos: undefined }))
  }

  const removePhoto = (key: string) =>
    setPhotos((prev) => {
      const gone = prev.find((d) => d.key === key)
      if (gone?.preview.startsWith('blob:')) URL.revokeObjectURL(gone.preview)
      return prev.filter((d) => d.key !== key)
    })

  const makeCover = (key: string) =>
    setPhotos((prev) => {
      const pick = prev.find((d) => d.key === key)
      return pick ? [pick, ...prev.filter((d) => d.key !== key)] : prev
    })

  const buildSlots = (): Omit<Slot, 'id' | 'listingId'>[] => {
    const out: Omit<Slot, 'id' | 'listingId'>[] = []

    if (availability === 'custom') {
      // One idle window per day in the range, at the hours they gave. A day
      // that has already ended is skipped, and today's window is clipped to
      // start now, so nothing is offered in the past.
      const from = parseDay(custom.from)!
      const until = parseDay(custom.until)!
      const start = parseClock(custom.start)!
      const end = parseClock(custom.end)!
      const now = Date.now()
      const days = Math.round((until.getTime() - from.getTime()) / 86_400_000)
      for (let d = 0; d <= days; d++) {
        const day = new Date(from.getFullYear(), from.getMonth(), from.getDate() + d)
        const opens = day.getTime() + start * 3_600_000
        const closes = day.getTime() + end * 3_600_000
        const first = Math.max(opens, now)
        if (closes - first < 30 * 60_000) continue
        out.push({
          start: new Date(first).toISOString(),
          end: new Date(closes).toISOString(),
          // Floored to the quarter hour: usable hours may never exceed the
          // window itself, which is a rule the catalog enforces too.
          hoursUsable: Math.floor(((closes - first) / 3_600_000) * 4) / 4,
        })
      }
      return out
    }

    const preset = AVAILABILITY.find((a) => a.id === availability)
    if (!preset) return out // 'none': editing, and no new windows
    const base = new Date()
    base.setHours(0, 0, 0, 0)
    // The next quarter hour: today's window starts from now, not from this morning.
    const now = Math.ceil(Date.now() / (15 * 60_000)) * 15 * 60_000
    const shortest = (isBatch ? 1 : minHours) * 3_600_000
    // Two weeks out is enough to look real without pretending to know December.
    for (let d = 0; d < 14; d++) {
      // Weekday of that date (Mon = 0), not the offset from today.
      const date = new Date(base.getFullYear(), base.getMonth(), base.getDate() + d)
      if (!preset.days.includes((date.getDay() + 6) % 7)) continue
      const opens = date.getTime() + preset.from * 3_600_000
      const closes = date.getTime() + preset.to * 3_600_000
      const first = Math.max(opens, now)
      // What is left of today must still fit the shortest booking.
      if (closes - first < shortest) continue
      out.push({
        start: new Date(first).toISOString(),
        end: new Date(closes).toISOString(),
        hoursUsable: Math.floor(((closes - first) / 3_600_000) * 4) / 4,
      })
    }
    return out
  }

  const submit = async () => {
    const e = validate()
    setErrors(e)
    setTouched({
      title: true,
      blurb: true,
      rate: true,
      instructions: true,
      machine: true,
      availability: true,
      photos: true,
      address: true,
    })
    if (Object.keys(e).length > 0 || !categoryId || !meta) {
      // After the errors render: take the person to the first one.
      requestAnimationFrame(() => {
        const first = document.querySelector<HTMLElement>('[aria-invalid="true"]')
        first?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        first?.focus({ preventScroll: true })
      })
      return
    }

    const shared = {
      category: categoryId,
      title: title.trim(),
      blurb: blurb.trim(),
      district,
      instructions: instructions.trim(),
      // Only what the owner chose: nothing is saved on their behalf.
      rules,
      active: was?.active ?? true,
      photos: photos.flatMap((p) => (p.url ? [p.url] : [])),
    }

    // Ids and the owner come from the server and the caller's token.
    const listing: repo.ListingDraft = isBatch
      ? {
          ...shared,
          mode: 'batch',
          machine: machine.trim(),
          ...(materials.length ? { materials } : {}),
          maxDims: dims,
          ...(wasBatch?.toleranceMm != null ? { toleranceMm: wasBatch.toleranceMm } : {}),
          unitsPerHour,
          setupHours,
          ratePerHour: rate,
          setupFee,
        }
      : {
          ...shared,
          mode: 'window',
          ratePerHour: rate,
          minHours,
          maxHours,
          extraFee,
          extraLabel: extraFee > 0 ? extraLabel.trim() || t('Consumables') : t('No extras'),
        }

    setSaving(true)
    try {
      if (was) {
        await repo.updateListing(was.id, listing, address.trim())
        const gone = (edit?.slots ?? []).filter((s) => !keptSlots.some((k) => k.id === s.id))
        await Promise.all(gone.map((s) => repo.removeSlot(was.id, s.id)))
        const added = buildSlots()
        if (added.length) await repo.addSlots(was.id, added)
        await Promise.all(
          [['myListings'], ['listing', was.id], ['offers', was.id]].map((queryKey) => qc.invalidateQueries({ queryKey })),
        )
        toast(t('{title} updated', { title: listing.title }))
      } else {
        await repo.addListing(listing, buildSlots(), address.trim())
        await qc.invalidateQueries({ queryKey: ['myListings'] })
        toast(t('{title} is live', { title: listing.title }))
      }
      nav('/earn', { replace: true })
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setSaving(false)
    }
  }

  /* --------------------------------------------- step 1: pick a category */
  if (!categoryId) {
    return (
      <Screen
        back="/earn"
        eyebrow="New listing"
        title={t('What are you lending?')}
        sub={t('Pick the closest thing. You can be specific on the next screen.')}
      >
        <ul className="ruled border-t border-[var(--line)]">
          {CATEGORIES.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => {
                  setCategoryId(c.id)
                  setRate((EXAMPLES[c.id] ?? DEFAULT_EXAMPLE).rate)
                }}
                className="flex w-full items-center gap-3 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-60"
              >
                <Icon
                  name={categoryIcon(c.icon)}
                  size={18}
                  strokeWidth={1.6}
                  className="shrink-0 text-[var(--ink-3)]"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-semibold">{c.label}</span>
                  <span className="t-sm block truncate text-[var(--ink-4)]">{c.blurb}</span>
                </span>
                <Icon
                  name="chevron-right"
                  size={16}
                  strokeWidth={1.8}
                  className="shrink-0 text-[var(--ink-4)]"
                />
              </button>
            </li>
          ))}
        </ul>
      </Screen>
    )
  }

  /* ------------------------------------------------ step 2: the details */
  return (
    <Screen
      back="/earn"
      eyebrow={was ? t('Edit listing') : t('New listing')}
      title={was ? was.title : t('List your {what}', { what: listYour(meta!.label) })}
      sub={was ? t('Changes show on the listing at once. Bookings already made keep what was agreed.') : t('Four minutes now, and the idle hours start paying.')}
      footer={
        <Button
          block
          size="lg"
          disabled={saving}
          // Keep focus where it is on press: blurring a time field first re-rendered
          // the form under the pointer and swallowed the click (submit validates anyway).
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => void submit()}
        >
          {was ? t('Save changes') : t('Publish listing')}
        </Button>
      }
    >
      <button
        disabled={Boolean(was)}
        onClick={() => setCategoryId(null)}
        className="mb-7 inline-flex min-h-[38px] items-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] px-3.5 text-[13.5px] font-semibold
          transition-colors duration-[160ms] hover:border-[var(--ink-4)]"
      >
        <Icon name={categoryIcon(meta!.icon)} size={17} className="text-[var(--accent-text)]" />
        {meta!.label}
        {!was && <Icon name="close" size={14} strokeWidth={2.4} className="text-[var(--ink-4)]" />}
      </button>

      <div className="space-y-6">
        <Field label={t('Name it')} error={errorFor('title')} htmlFor="f-title">
          <Input
            id="f-title"
            value={title}
            invalid={Boolean(errorFor('title'))}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={blur('title')}
            placeholder={t(example.title)}
          />
        </Field>

        <Field
          label={t('Photos')}
          hint={t('Your own pictures of the actual thing. The first one is the cover.')}
          error={errorFor('photos')}
        >
          <div className="grid grid-cols-3 gap-2">
            {photos.map((p, i) => {
              const pending = !p.url && !p.error
              return (
                <div
                  key={p.key}
                  className="relative aspect-[4/3] overflow-hidden rounded-[var(--radius-field)] bg-[var(--sunken)]"
                >
                  <img
                    src={p.preview}
                    alt=""
                    className={`h-full w-full object-cover transition-opacity duration-[200ms] ${pending ? 'opacity-40' : ''}`}
                  />
                  {pending && (
                    <span className="absolute inset-0 grid place-items-center text-[12px] font-semibold text-[var(--ink-2)]">
                      {t('Uploading…')}
                    </span>
                  )}
                  {i === 0 && p.url && (
                    <span className="absolute left-2 top-2 rounded-full bg-[var(--ink)] px-2 py-0.5 text-[11px] font-semibold text-[var(--on-inverse)]">
                      {t('Cover')}
                    </span>
                  )}
                  {p.error && (
                    <span className="absolute inset-x-0 bottom-0 bg-[var(--danger)] px-2 py-1 text-[11px] font-semibold leading-tight text-white">
                      {p.error}
                    </span>
                  )}
                  <button
                    type="button"
                    aria-label={t('Remove photo')}
                    onClick={() => removePhoto(p.key)}
                    className="tap absolute right-1.5 top-1.5 grid h-7 w-7 place-items-center rounded-full bg-[var(--ink)] text-[var(--on-inverse)]"
                  >
                    <Icon name="close" size={13} strokeWidth={2.6} />
                  </button>
                  {i > 0 && p.url && (
                    <button
                      type="button"
                      onClick={() => makeCover(p.key)}
                      className="absolute inset-x-1.5 bottom-1.5 rounded-full bg-white/90 py-1 text-[11px] font-semibold text-[var(--ink)]"
                    >
                      {t('Make cover')}
                    </button>
                  )}
                </div>
              )
            })}
            {photos.length < MAX_PHOTOS && (
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="grid aspect-[4/3] place-items-center rounded-[var(--radius-field)] border border-dashed border-[var(--line-strong)] text-[var(--ink-3)] transition-colors duration-[160ms] hover:border-[var(--ink)] hover:text-[var(--ink)]"
              >
                <span className="flex flex-col items-center gap-1 text-[12px] font-semibold">
                  <Icon name="camera" size={20} strokeWidth={1.8} />
                  {photos.length ? t('Add another') : t('Add photos')}
                </span>
              </button>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            aria-label={t('Choose photos')}
            onChange={(e) => {
              void addPhotos(e.target.files)
              e.target.value = ''
            }}
          />
        </Field>

        <Field
          label={t('One line about it')}
          hint={t('What a neighbour would want to know before asking.')}
          error={errorFor('blurb')}
          htmlFor="f-blurb"
        >
          <Textarea
            id="f-blurb"
            rows={2}
            value={blurb}
            invalid={Boolean(errorFor('blurb'))}
            onChange={(e) => setBlurb(e.target.value)}
            onBlur={blur('blurb')}
            placeholder={t(example.blurb)}
          />
        </Field>

        {isBatch && (
          <>
            <Field label={t('Machine')} error={errorFor('machine')} htmlFor="f-machine">
              <Input
                id="f-machine"
                value={machine}
                invalid={Boolean(errorFor('machine'))}
                onChange={(e) => setMachine(e.target.value)}
                onBlur={blur('machine')}
                placeholder={t(example.machine ?? example.title)}
              />
            </Field>

            {categoryId && TAKES_MATERIALS.includes(categoryId) && (
            <Field label={t('Materials you stock')} hint={t('Tap all that apply, if any.')}>
              <div className="flex flex-wrap gap-2">
                {MATERIALS.map((m) => (
                  <Chip
                    key={m}
                    selected={materials.includes(m)}
                    onClick={() =>
                      setMaterials((prev) =>
                        prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m],
                      )
                    }
                  >
                    {t(m)}
                  </Chip>
                ))}
              </div>
            </Field>
            )}

            <Field
              label={t('Parts per hour')}
              hint={t('Roughly, once it is set up. This is what turns a quantity into a delivery date.')}
              htmlFor="f-throughput"
            >
              <Input
                id="f-throughput"
                inputMode="numeric"
                className="tnum"
                value={unitsPerHour}
                onChange={(e) => setUnitsPerHour(Math.max(0.1, Number(e.target.value) || 0.1))}
              />
            </Field>

            <Field label={t('Setup time')} hint={t('Hours to get a job going, before the first part.')} htmlFor="f-setup-hours">
              <Input
                id="f-setup-hours"
                inputMode="decimal"
                className="tnum"
                value={setupHours}
                onChange={(e) => setSetupHours(Math.max(0, Number(e.target.value.replace(',', '.')) || 0))}
              />
            </Field>

            <fieldset>
              <legend className="t-label">{t('Largest job it takes (mm)')}</legend>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {(['x', 'y', 'z'] as const).map((axis) => (
                  <label key={axis} className="block">
                    <span className="t-sm text-[var(--ink-3)]">{t({ x: 'Length', y: 'Width', z: 'Height' }[axis])}</span>
                    <Input
                      inputMode="numeric"
                      className="tnum"
                      value={dims[axis]}
                      onChange={(e) => setDims((d) => ({ ...d, [axis]: Math.max(1, Number(e.target.value) || 1) }))}
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          </>
        )}

        <Field label={t('Where is it?')} htmlFor="f-district">
          <DistrictSelect
            id="f-district"
            districts={districts.data ?? {}}
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
          />
        </Field>

        <Field
          label={t('Address')}
          hint={t('Only shared with the buyer once you accept their request.')}
          error={errorFor('address')}
          htmlFor="f-address"
        >
          <Input
            id="f-address"
            autoComplete="street-address"
            maxLength={200}
            value={address}
            invalid={Boolean(errorFor('address'))}
            onChange={(e) => setAddress(e.target.value)}
            onBlur={blur('address')}
            placeholder="Oranienstraße 12, 10999 Berlin"
          />
        </Field>

        <Field label={t('Price')} error={errorFor('rate')} htmlFor="f-rate">
          <MoneyInput id="f-rate" cents={rate} onCents={setRate} invalid={Boolean(errorFor('rate'))} />
        </Field>

        {isBatch ? (
          <Field label={t('Setup fee')} hint={t('Charged once per job, for programming and fixturing.')} htmlFor="f-setup">
            <MoneyInput id="f-setup" cents={setupFee} onCents={setSetupFee} suffix={t('per job')} />
          </Field>
        ) : (
          <>
            <Field label={t('Shortest and longest booking')}>
              <div className="flex items-center gap-3">
                <Input
                  inputMode="numeric"
                  aria-label={t('Minimum hours')}
                  className="tnum"
                  value={minHours}
                  onChange={(e) => setMinHours(Math.max(1, Number(e.target.value) || 1))}
                />
                <span className="shrink-0 text-[14px] text-[var(--ink-4)]">{t('to')}</span>
                <Input
                  inputMode="numeric"
                  aria-label={t('Maximum hours')}
                  className="tnum"
                  value={maxHours}
                  onChange={(e) => setMaxHours(Math.max(minHours, Number(e.target.value) || minHours))}
                />
                <span className="shrink-0 text-[14px] text-[var(--ink-4)]">{t('hours')}</span>
              </div>
            </Field>

            <Field
              label={t('One-off extra')}
              hint={t('Detergent, fuel, gas, anything you top up between bookings. Leave at zero if there is none.')}
              htmlFor="f-extra"
            >
              <MoneyInput id="f-extra" cents={extraFee} onCents={setExtraFee} suffix={t('per booking')} />
              {extraFee > 0 && (
                <div className="mt-2">
                  <Input
                    aria-label={t('What the extra covers')}
                    value={extraLabel}
                    onChange={(e) => setExtraLabel(e.target.value)}
                    placeholder={t('Detergent and softener')}
                  />
                </div>
              )}
            </Field>
          </>
        )}

        {was && (
          <Field label={t('Windows already listed')} hint={t('Remove any that are no longer free.')}>
            {keptSlots.length === 0 ? (
              <p className="t-sm text-[var(--ink-3)]">{t('None coming up.')}</p>
            ) : (
              <ul className="ruled border-t border-[var(--line)]">
                {keptSlots.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="t-sm tnum">{range(s.start, s.end)}</span>
                    <Button
                      size="sm"
                      variant="quiet"
                      aria-label={t('Remove the window {when}', { when: range(s.start, s.end) })}
                      onClick={() => setKeptSlots((prev) => prev.filter((k) => k.id !== s.id))}
                    >
                      {t('Remove')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Field>
        )}

        <Field
          label={was ? t('Add more free time') : t('When is it free?')}
          hint={t('Pick a pattern, or type the exact dates and hours. You can change them later.')}
          error={errorFor('availability')}
        >
          <div className="space-y-2">
            {[
              ...(was ? [{ id: 'none' as const, label: 'No new windows', detail: 'Keep what is listed' }] : []),
              ...AVAILABILITY,
              { id: 'custom' as Availability, label: 'Pick the dates myself', detail: customSummary(custom) },
            ].map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setAvailability(a.id)}
                aria-pressed={availability === a.id}
                aria-controls={a.id === 'custom' ? 'custom-window' : undefined}
                aria-expanded={a.id === 'custom' ? availability === 'custom' : undefined}
                className={`flex min-h-[62px] w-full items-center gap-3.5 rounded-[var(--radius-field)] border px-4 text-left transition-colors duration-[160ms] ${
                  availability === a.id
                    ? 'border-[var(--ink)] bg-[var(--sunken)]'
                    : 'border-[var(--line-strong)] bg-[var(--surface)] hover:border-[var(--ink-4)]'
                }`}
              >
                <span
                  className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 transition-colors duration-[160ms] ${
                    availability === a.id
                      ? 'border-[var(--ink)] bg-[var(--ink)] text-[var(--on-inverse)]'
                      : 'border-[var(--line-strong)]'
                  }`}
                >
                  {availability === a.id && <Icon name="check" size={12} strokeWidth={3.5} />}
                </span>
                <span className="min-w-0">
                  <span className="block text-[15px] font-semibold">{t(a.label)}</span>
                  <span className="tnum block text-[13px] text-[var(--ink-3)]">{t(a.detail)}</span>
                </span>
              </button>
            ))}

            {availability === 'custom' && (
              <div
                id="custom-window"
                className="space-y-3 rounded-[var(--radius-field)] border border-[var(--line-strong)] bg-[var(--surface)] p-4"
              >
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('From')}</span>
                    <Input
                      type="date"
                      value={custom.from}
                      min={isoDay(new Date())}
                      invalid={Boolean(errorFor('availability'))}
                      onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))}
                      onBlur={blur('availability')}
                      className="tnum"
                    />
                  </label>
                  <label className="block">
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('Until')}</span>
                    <Input
                      type="date"
                      value={custom.until}
                      min={custom.from || isoDay(new Date())}
                      invalid={Boolean(errorFor('availability'))}
                      onChange={(e) => setCustom((c) => ({ ...c, until: e.target.value }))}
                      onBlur={blur('availability')}
                      className="tnum"
                    />
                  </label>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('Free from')}</span>
                    <Input
                      type="time"
                      step={900}
                      value={custom.start}
                      invalid={Boolean(errorFor('availability'))}
                      onChange={(e) => setCustom((c) => ({ ...c, start: e.target.value }))}
                      onBlur={blur('availability')}
                      className="tnum"
                    />
                  </label>
                  <label className="block">
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('Until')}</span>
                    <Input
                      type="time"
                      step={900}
                      value={custom.end}
                      invalid={Boolean(errorFor('availability'))}
                      onChange={(e) => setCustom((c) => ({ ...c, end: e.target.value }))}
                      onBlur={blur('availability')}
                      className="tnum"
                    />
                  </label>
                </div>
                <p className="tnum text-[13px] text-[var(--ink-3)]">
                  {customProblem(custom)
                    ? t('Each day in the range gets one idle window at those hours.')
                    : t('{days}, {first} to {last}, free {start} – {end} each day.', {
                        days: plural(customDayCount(custom), '{n} day', '{n} days'),
                        first: `${weekday(parseDay(custom.from)!)} ${shortDate(parseDay(custom.from)!)}`,
                        last: `${weekday(parseDay(custom.until)!)} ${shortDate(parseDay(custom.until)!)}`,
                        start: custom.start,
                        end: custom.end,
                      })}
                </p>
              </div>
            )}
          </div>
        </Field>

        <Field
          label={t('How does someone get it?')}
          hint={t('Only shown after you accept a request.')}
          error={errorFor('instructions')}
          htmlFor="f-instructions"
        >
          <Textarea
            id="f-instructions"
            rows={3}
            value={instructions}
            invalid={Boolean(errorFor('instructions'))}
            onChange={(e) => setInstructions(e.target.value)}
            onBlur={blur('instructions')}
            placeholder={t('Side entrance, doorbell marked Brandt. Pods are in the glass jar.')}
          />
        </Field>

        <Field label={t('House rules')} hint={t('Optional, but they prevent most of the awkward messages.')}>
          <div className="flex flex-wrap gap-2">
            {RULE_SUGGESTIONS.map((en) => t(en)).map((r) => (
              <Chip
                key={r}
                selected={rules.includes(r)}
                onClick={() =>
                  setRules((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))
                }
              >
                {r}
              </Chip>
            ))}
          </div>
        </Field>

        <Card className="p-5">
          <p className="t-label mb-2 text-[var(--ink-2)]">{t('What a booking would earn you')}</p>
          <p className="t-plate tnum text-[38px] leading-[42px] text-[var(--ink)]">
            {formatEur(
              Math.round((rate * (isBatch ? 4 : minHours) + (isBatch ? setupFee : extraFee)) * 0.85),
            )}
          </p>
          <p className="t-sm mt-1.5 text-[var(--ink-2)]">
            {isBatch
              ? t('for a four-hour run, after the 15 % Cappy fee.')
              : t('for a {n}-hour booking, after the 15 % Cappy fee.', { n: minHours })}
          </p>
        </Card>

        <Banner
          tone="warn"
          title={t('Paid through Cappy')}
          body={t('Buyers pay by card when you accept. Your share goes to your bank once the booking is done; set up payouts under Earn.')}
        />
      </div>
    </Screen>
  )
}
