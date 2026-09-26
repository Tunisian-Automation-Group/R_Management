import { useEffect, useRef, useState } from 'react'
import { drafts } from '../device.ts'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type { CancellationPolicy, CategoryId, Material, Slot, WeeklyRule } from '../../domain/types.ts'
import { CATEGORIES, category, durationLabel } from '../../domain/categories.ts'
import { formatMoney } from '../../domain/money.ts'
import { messageOf, useCappy, useToast } from '../store.tsx'
import { useSession } from '../../data/auth.ts'
import { askForPush } from '../components/PushPrime.tsx'
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
  Segmented,
  Textarea,
} from '../components/ui.tsx'
import { DistrictSelect } from '../components/DistrictSelect.tsx'
import { NotFound } from './NotFound.tsx'
import { POLICIES, clockTime, percent, policyName, policyText, range, sentence } from '../format.ts'
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

type Availability = 'evenings' | 'workday' | 'weekend' | 'always' | 'weekly' | 'custom'

/** A row of the weekly editor: these ISO weekdays (Mon = 1), these hours. */
type WeekRow = { days: number[]; start: string; end: string }

const EVERY_DAY = [1, 2, 3, 4, 5, 6, 7]
// Habits, not dates: each is a weekly schedule the server keeps 8 weeks ahead
// in the listing's time zone (H-4). Two weeks of windows made once in the
// browser used to leave a listing with nothing free after a fortnight.
const AVAILABILITY: { id: Availability; label: string; days: number[]; start: string; end: string }[] = [
  { id: 'evenings', label: 'Evenings', days: EVERY_DAY, start: '18:00', end: '23:00' },
  { id: 'workday', label: 'While I am at work', days: [1, 2, 3, 4, 5], start: '09:00', end: '18:00' },
  { id: 'weekend', label: 'Weekends', days: [6, 7], start: '09:00', end: '20:00' },
  { id: 'always', label: 'Most of the time', days: EVERY_DAY, start: '07:00', end: '22:00' },
]

/** Monday first, in the reader's language: "Mon", "lun.", "Mo." (1 Jan 2024 was a Monday). */
const isoWeekday = (d: number) => new Date(2024, 0, d).toLocaleDateString(locale(), { weekday: 'short' })

/** "Mon–Fri", "every day", "Sat, Sun". */
function daysLabel(days: number[]): string {
  const ds = [...new Set(days)].sort()
  if (ds.length === 7) return t('every day')
  const run = ds.every((d, i) => i === 0 || d === ds[i - 1] + 1)
  return run && ds.length > 2 ? `${isoWeekday(ds[0])}–${isoWeekday(ds[ds.length - 1])}` : ds.map(isoWeekday).join(', ')
}

/** "18:00 – 23:00, every day" in the reader's clock. */
const rowLabel = (r: WeekRow) => `${clockTime(r.start)} – ${clockTime(r.end)}, ${daysLabel(r.days)}`

const rowsToRules = (rows: WeekRow[]): WeeklyRule[] =>
  rows.flatMap((r) => [...new Set(r.days)].sort().map((day) => ({ day, start: r.start, end: r.end })))

/** The rules grouped back into rows by their hours, for the editor. */
function rulesToRows(rules: WeeklyRule[]): WeekRow[] {
  const byHours = new Map<string, WeekRow>()
  for (const r of rules) {
    const k = `${r.start}-${r.end}`
    const row = byHours.get(k) ?? { days: [], start: r.start, end: r.end }
    row.days.push(r.day)
    byHours.set(k, row)
  }
  return [...byHours.values()]
}

/** Why a weekly schedule cannot be saved, or null. */
function weeklyProblem(rows: WeekRow[]): string | null {
  if (!rows.length || rows.some((r) => !r.days.length)) return t('Pick at least one day for each time.')
  for (const r of rows) {
    const s = parseClock(r.start)
    const e = r.end === '24:00' ? 24 : parseClock(r.end)
    if (s === null || e === null) return t('Pick the hours it is free on those days.')
    if (e <= s) return t('It has to stop being free after it starts being free.')
    if (e - s < 0.5) return t('Give people at least half an hour.')
  }
  return null
}

const deviceTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Berlin'

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
  return `${days}, ${clockTime(c.start)} – ${clockTime(c.end)}`
}

type Errors = Partial<
  Record<'title' | 'blurb' | 'rate' | 'instructions' | 'machine' | 'availability' | 'photos' | 'address' | 'postalCode', string>
>

/** A photograph on its way in: shown at once from the file, sent shrunk, and
 *  carrying the server's URL once it has one. The first in the list is the cover. */
/** A picture in the form: `progress` 0–1 while it goes up, `file` kept so a failed one can be retried (U-25). */
type PhotoDraft = { key: string; preview: string; url?: string; error?: string; progress?: number; file?: File }

/** The server's field paths (`listing.ratePerHour`, `address`) as this form's fields. */
const FIELD_OF: Record<string, keyof Errors> = {
  title: 'title', blurb: 'blurb', ratePerHour: 'rate', instructions: 'instructions', machine: 'machine',
  address: 'address', postalCode: 'postalCode', photos: 'photos', availability: 'availability', slots: 'availability',
}
function fieldErrors(fields?: { field: string; message: string }[]): Errors {
  const e: Errors = {}
  for (const f of fields ?? []) {
    const key = FIELD_OF[f.field.split('.').pop() ?? f.field] ?? FIELD_OF[f.field.split('.')[0]]
    if (key && !e[key]) e[key] = t(f.message)
  }
  return e
}

/** New listing at /earn/new; editing one of yours at /earn/edit/:id. */
const clampPct = (v: string) => Math.max(0, Math.min(50, Math.round(Number(v) || 0)))

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
  const attempt = repo.useAttemptKey()
  const districts = repo.useDistricts()
  const [saving, setSaving] = useState(false)
  const was = edit?.listing
  // Priced in the owner's market's currency (M-2): the server sets it; the form
  // only shows the right symbol. Nothing sends a currency, so nothing sends EUR.
  const market = repo.useMarket()
  const cur = was?.currency ?? market.currency
  // The whole form survives a reload or a session expiring mid-form, for a new
  // listing and for an edit alike, one draft per listing (U-10, V3-10).
  const draftKey = `listing.${was?.id ?? 'new'}`
  const [draft] = useState<Record<string, unknown>>(() => {
    try {
      return JSON.parse(drafts.get(draftKey) ?? '{}') as Record<string, unknown>
    } catch {
      return {}
    }
  })
  /** The draft's value when there is one, else what the listing had, else the default. */
  const init = <T,>(key: string, fallback: T): T => (key in draft ? (draft[key] as T) : fallback)
  const wasWindow = was?.mode === 'window' ? was : undefined
  const wasBatch = was?.mode === 'batch' ? was : undefined

  const [categoryId, setCategoryId] = useState<CategoryId | null>(init('categoryId', was?.category ?? null))
  const [title, setTitle] = useState(init('title', was?.title ?? ''))
  const [blurb, setBlurb] = useState(init('blurb', was?.blurb ?? ''))
  const [district, setDistrict] = useState(init('district', was?.district ?? (state.search.district || 'Kreuzberg')))
  // Only places in the owner's own country (V5-2): the server refuses the rest
  // (district_not_in_country), and a listing is priced in its market's currency.
  const localDistricts = Object.fromEntries(Object.entries(districts.data ?? {}).filter(([, d]) => d.country === market.country))
  const firstLocal = Object.keys(localDistricts).sort()[0]
  useEffect(() => {
    if (districts.data && firstLocal && !localDistricts[district]) setDistrict(firstLocal)
  }, [districts.data, firstLocal, district]) // eslint-disable-line react-hooks/exhaustive-deps
  const [address, setAddress] = useState(init('address', edit?.address ?? ''))
  const [rate, setRate] = useState(init('rate', was?.ratePerHour ?? 400))
  const [extraFee, setExtraFee] = useState(init('extraFee', wasWindow?.extraFee ?? 0))
  const [extraLabel, setExtraLabel] = useState(
    init('extraLabel', wasWindow && wasWindow.extraFee > 0 ? wasWindow.extraLabel : t('Consumables')),
  )
  const [minHours, setMinHours] = useState(init('minHours', wasWindow?.minHours ?? 1))
  const [maxHours, setMaxHours] = useState(init('maxHours', wasWindow?.maxHours ?? 6))
  const [machine, setMachine] = useState(init('machine', wasBatch?.machine ?? ''))
  const [materials, setMaterials] = useState<Material[]>(init('materials', wasBatch?.materials ?? []))
  const [unitsPerHour, setUnitsPerHour] = useState(init('unitsPerHour', wasBatch?.unitsPerHour ?? 10))
  // The most one booking takes (two pallet spaces on a van); empty means no cap (V5-22).
  const [maxQuantity, setMaxQuantity] = useState<string>(init('maxQuantity', wasBatch?.maxQuantity ? String(wasBatch.maxQuantity) : ''))
  const [setupFee, setSetupFee] = useState(init('setupFee', wasBatch?.setupFee ?? 1500))
  const [setupHours, setSetupHours] = useState(init('setupHours', wasBatch?.setupHours ?? 1))
  const [dims, setDims] = useState(init('dims', wasBatch?.maxDims ?? { x: 300, y: 300, z: 300 }))
  // Editing: the windows already listed stay unless removed; new ones are optional.
  const [availability, setAvailability] = useState<Availability | 'none'>(init('availability', edit ? 'none' : 'evenings'))
  const [custom, setCustom] = useState<CustomWindow>(init('custom', defaultCustom))
  const [weekRows, setWeekRows] = useState<WeekRow[]>(
    init('weekRows', was?.availability?.weekly.length ? rulesToRows(was.availability.weekly) : [{ days: [1, 2, 3, 4, 5], start: '09:00', end: '18:00' }]),
  )
  // Editing a listing that repeats weekly: stop the schedule (and the windows it made).
  const [stopSchedule, setStopSchedule] = useState<boolean>(init('stopSchedule', false))
  const [postalCode, setPostalCode] = useState<string>(init('postalCode', was?.postalCode ?? ''))
  const [keptSlots, setKeptSlots] = useState<Slot[]>(init('keptSlots', edit?.slots ?? []))
  // A weekly schedule makes dozens of windows: the first few, then all on request (V5-32).
  // ponytail: the slot answer does not say which the schedule made; hide those when it does.
  const [allSlots, setAllSlots] = useState(false)
  const [instructions, setInstructions] = useState(init('instructions', was?.instructions ?? ''))
  const [instantBook, setInstantBook] = useState(init('instantBook', was?.instantBook ?? false))
  const [policy, setPolicy] = useState<CancellationPolicy>(init('policy', was?.cancellationPolicy ?? 'flexible'))
  const [dayPct, setDayPct] = useState(init('dayPct', was?.dayDiscountPct ?? 0))
  const [weekPct, setWeekPct] = useState(init('weekPct', was?.weekDiscountPct ?? 0))
  const [rules, setRules] = useState<string[]>(init('rules', was?.rules.filter((r) => r !== 'Cash or bank transfer') ?? []))
  // Photos in the draft are the ones already uploaded (they have a url); one
  // still uploading when the page went away has to be picked again.
  const [photos, setPhotos] = useState<PhotoDraft[]>(
    init<string[]>('photos', was?.photos ?? []).map((url, i) => ({ key: `was-${i}`, preview: repo.mediaUrl(url), url })),
  )
  const fileInput = useRef<HTMLInputElement>(null)
  const [errors, setErrors] = useState<Errors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const meta = categoryId ? category(categoryId) : null
  const isBatch = meta?.mode === 'batch'
  const form = {
    categoryId, title, blurb, district, address, rate, extraFee, extraLabel, minHours, maxHours, machine, materials,
    unitsPerHour, setupFee, setupHours, dims, availability, custom, keptSlots, instructions, instantBook, policy,
    dayPct, weekPct, rules, photos: photos.flatMap((p) => (p.url ? [p.url] : [])), weekRows, stopSchedule, postalCode, maxQuantity,
  }
  const formJson = JSON.stringify(form)
  // Written only once something changed, so an untouched edit never shadows the listing.
  const firstJson = useRef(formJson)
  useEffect(() => {
    if (formJson !== firstJson.current) drafts.set(draftKey, formJson)
  }, [draftKey, formJson])
  const restored = Object.keys(draft).length > 0
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
    if (address.trim().length < 5) e.address = t('Add the hand-over address; renters see it only after you accept.')
    if (postalCode.trim().length > 16) e.postalCode = t('That postal code is too long.')
    if (isBatch && machine.trim().length < 2) e.machine = t('Which machine is it?')
    if (photos.some((p) => !p.url && !p.error)) e.photos = t('Give the photos a moment to finish uploading.')
    if (availability === 'custom') {
      const problem = customProblem(custom)
      if (problem) e.availability = problem
    }
    if (availability === 'weekly') {
      const problem = weeklyProblem(weekRows)
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
      file: f,
      progress: 0,
    }))
    setPhotos((prev) => [...prev, ...drafts])
    setTouched((t) => ({ ...t, photos: true }))
    await Promise.all(drafts.map((d) => upload(d.key, d.file!)))
    setErrors((prev) => ({ ...prev, photos: undefined }))
  }

  const patchPhoto = (key: string, patch: Partial<PhotoDraft>) =>
    setPhotos((prev) => prev.map((d) => (d.key === key ? { ...d, ...patch } : d)))

  /** Shrink, then send with progress; a failure stays in the grid with its reason and a retry. */
  const upload = async (key: string, file: File) => {
    patchPhoto(key, { error: undefined, progress: 0 })
    try {
      const url = await repo.uploadPhoto(await shrink(file), file.name.replace(/\.[^.]*$/, '') + '.jpg', (progress) =>
        patchPhoto(key, { progress }),
      )
      patchPhoto(key, { url, progress: undefined, file: undefined })
    } catch (err) {
      patchPhoto(key, { error: err instanceof Error ? err.message : t('Upload failed'), progress: undefined })
    }
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
      // The next quarter hour, as below: a retried create sends the same body (FL-1).
      // ponytail: a retry across a quarter-hour boundary is a new key, and the server may keep both tries.
      const now = Math.ceil(Date.now() / (15 * 60_000)) * 15 * 60_000
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

    // Presets and the weekly editor are schedules the server rolls forward (H-4);
    // 'none' adds nothing. Only exact dates are windows made here.
    return out
  }

  /** The weekly schedule to send: a preset or the editor's rows; `null` stops
   *  one; `undefined` leaves it as it is (the key is left out). */
  const availabilityOut = (): repo.ListingDraft['availability'] => {
    const timeZone = was?.availability?.timeZone ?? deviceTimeZone()
    const preset = AVAILABILITY.find((a) => a.id === availability)
    if (preset) return { weekly: rowsToRules([preset]), timeZone }
    if (availability === 'weekly') return { weekly: rowsToRules(weekRows), timeZone }
    if (stopSchedule) return null
    return undefined
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

    // ponytail: the point is the district's centre until addresses are geocoded
    // (M-7); the server keeps it within 30 km of the district and shows others
    // a ~500 m grid, the exact point only in an accepted booking's hand-over.
    const d = districts.data?.[district]
    const location = was?.location && was.district === district ? was.location : d ? { lat: d.lat, lng: d.lng } : undefined
    const schedule = availabilityOut()
    const shared = {
      category: categoryId,
      title: title.trim(),
      blurb: blurb.trim(),
      district,
      ...(location ? { location } : {}),
      ...(d?.country ? { country: d.country } : {}),
      ...(postalCode.trim() ? { postalCode: postalCode.trim() } : {}),
      ...(schedule !== undefined ? { availability: schedule } : {}),
      instructions: instructions.trim(),
      // Only what the owner chose: nothing is saved on their behalf.
      rules,
      active: was?.active ?? true,
      photos: photos.flatMap((p) => (p.url ? [p.url] : [])),
      instantBook,
      cancellationPolicy: policy,
      dayDiscountPct: dayPct,
      weekDiscountPct: weekPct,
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
          ...(Number(maxQuantity) >= 1 ? { maxQuantity: Math.floor(Number(maxQuantity)) } : {}),
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
        drafts.set(draftKey, '')
        // A new owner raising the price past the review line puts the listing
        // back in the queue (FL-4): say so rather than "updated".
        const held = await repo.listingHeld(was.id).catch(() => false)
        toast(
          held
            ? t('{title} is saved and waiting for a quick check before people can book it', { title: listing.title })
            : t('{title} updated', { title: listing.title }),
        )
      } else {
        const slots = buildSlots()
        let created: Awaited<ReturnType<typeof repo.addListing>>
        try {
          created = await repo.addListing(listing, slots, address.trim(), attempt.keyFor({ listing, slots, address: address.trim() }))
        } catch (err) {
          attempt.settle(err)
          throw err
        }
        attempt.settle()
        drafts.set(draftKey, '')
        await qc.invalidateQueries({ queryKey: ['myListings'] })
        toast(
          created.held
            ? t('{title} is saved and waiting for a quick check before people can book it', { title: listing.title })
            : t('{title} is live', { title: listing.title }),
        )
        askForPush('listing')
      }
      nav('/earn', { replace: true })
    } catch (err) {
      // A server that checked the form says which fields: each error goes under its own (V4-20).
      const onForm = err instanceof repo.ApiError ? fieldErrors(err.fields) : {}
      if (Object.keys(onForm).length) {
        setErrors((prev) => ({ ...prev, ...onForm }))
        setTouched((prev) => ({ ...prev, ...Object.fromEntries(Object.keys(onForm).map((k) => [k, true])) }))
      }
      toast(messageOf(err), 'error')
    } finally {
      setSaving(false)
    }
  }

  /* --------------------------------------------- step 1: pick a category */
  if (!categoryId) {
    return (
      <Screen
        back="/earn"
        eyebrow={t('New listing')}
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
                className="flex w-full items-center gap-3 py-3.5 text-left transition-opacity duration-[var(--dur-short)] hover:opacity-60"
              >
                <Icon
                  name={categoryIcon(c.icon)}
                  size={18}
                  strokeWidth={1.6}
                  className="shrink-0 text-[var(--ink-3)]"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-body font-semibold">{c.label}</span>
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
      {restored && (
        <div className="mb-6">
          <Banner
            tone="warn"
            title={t('Your unsaved changes are back')}
            body={was ? t('They are not on the listing yet: save to publish them.') : t('Carry on where you left off.')}
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  drafts.set(draftKey, '')
                  location.reload()
                }}
              >
                {t('Discard')}
              </Button>
            }
          />
        </div>
      )}
      <button
        disabled={Boolean(was)}
        onClick={() => setCategoryId(null)}
        className="mb-7 inline-flex min-h-[38px] items-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] px-3.5 text-label font-semibold
          transition-colors duration-[var(--dur-short)] hover:border-[var(--ink-4)]"
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
                    className={`h-full w-full object-cover transition-opacity duration-[var(--dur-medium)] ${pending ? 'opacity-40' : ''}`}
                  />
                  {pending && (
                    <span className="absolute inset-0 grid place-items-center text-label font-semibold text-[var(--ink-2)]">
                      <span role="status">
                        {p.progress ? t('Uploading… {pct}', { pct: percent(p.progress) }) : t('Uploading…')}
                      </span>
                      <span
                        aria-hidden
                        className="absolute inset-x-0 bottom-0 h-1 bg-[var(--accent)] transition-[width] duration-[var(--dur-short)]"
                        style={{ width: `${Math.round((p.progress ?? 0) * 100)}%` }}
                      />
                    </span>
                  )}
                  {i === 0 && p.url && (
                    <span className="absolute left-2 top-2 rounded-full bg-[var(--ink)] px-2 py-0.5 text-caption font-semibold text-[var(--on-inverse)]">
                      {t('Cover')}
                    </span>
                  )}
                  {p.error && (
                    <span className="absolute inset-x-0 bottom-0 flex items-end gap-1 bg-[var(--danger)] px-2 py-1 text-caption font-semibold leading-tight text-[var(--on-status)]">
                      <span className="min-w-0 flex-1" role="alert">
                        {p.error}
                      </span>
                      {p.file && (
                        <button
                          type="button"
                          onClick={() => void upload(p.key, p.file!)}
                          className="min-h-6 shrink-0 rounded-full bg-[var(--surface)] px-2 text-[var(--danger)]"
                        >
                          {t('Retry')}
                        </button>
                      )}
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
                      className="absolute inset-x-1.5 bottom-1.5 min-h-6 rounded-full bg-[var(--veil)] py-1 text-caption font-semibold text-[var(--ink)]"
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
                className="grid aspect-[4/3] place-items-center rounded-[var(--radius-field)] border border-dashed border-[var(--line-strong)] text-[var(--ink-3)] transition-colors duration-[var(--dur-short)] hover:border-[var(--ink)] hover:text-[var(--ink)]"
              >
                <span className="flex flex-col items-center gap-1 text-label font-semibold">
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
            {/* Freight runs on a vehicle, counted in pallets (V5-22). */}
            <Field label={categoryId === 'freight' ? t('Vehicle') : t('Machine')} error={errorFor('machine')} htmlFor="f-machine">
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
              label={categoryId === 'freight' ? t('Pallets loaded per hour') : t('Parts per hour')}
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

            <Field
              label={t('Most per booking (optional)')}
              hint={categoryId === 'freight' ? t('How many pallet spaces you have free, say 2.') : t('Leave empty if there is no limit.')}
              htmlFor="f-max-qty"
            >
              <Input id="f-max-qty" inputMode="numeric" className="tnum" value={maxQuantity} onChange={(e) => setMaxQuantity(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </Field>

            <Field
              label={categoryId === 'freight' ? t('Loading time') : t('Setup time')}
              hint={categoryId === 'freight' ? t('Hours to load and secure the goods before you drive.') : t('Hours to get a job going, before the first part.')}
              htmlFor="f-setup-hours"
            >
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
            districts={localDistricts}
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
            placeholder={t('Street and number, city')}
          />
        </Field>

        <Field
          label={t('Postal code')}
          hint={t('Optional. Only shared with the buyer once you accept, with the address.')}
          error={errorFor('postalCode')}
          htmlFor="f-postal"
        >
          <Input
            id="f-postal"
            autoComplete="postal-code"
            maxLength={16}
            className="tnum"
            value={postalCode}
            invalid={Boolean(errorFor('postalCode'))}
            onChange={(e) => setPostalCode(e.target.value)}
            onBlur={blur('postalCode')}
          />
        </Field>

        <Field label={t('Price')} error={errorFor('rate')} htmlFor="f-rate">
          <MoneyInput id="f-rate" cents={rate} onCents={setRate} invalid={Boolean(errorFor('rate'))} currency={cur} />
        </Field>

        {isBatch ? (
          <Field
            label={categoryId === 'freight' ? t('Loading fee') : t('Setup fee')}
            hint={categoryId === 'freight' ? t('Charged once per trip, for loading.') : t('Charged once per job, for programming and fixturing.')}
            htmlFor="f-setup"
          >
            <MoneyInput id="f-setup" cents={setupFee} onCents={setSetupFee} suffix={t('per job')} currency={cur} />
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
                <span className="shrink-0 text-body text-[var(--ink-4)]">{t('to')}</span>
                <Input
                  inputMode="numeric"
                  aria-label={t('Maximum hours')}
                  className="tnum"
                  value={maxHours}
                  onChange={(e) => setMaxHours(Math.max(minHours, Number(e.target.value) || minHours))}
                />
                <span className="shrink-0 text-body text-[var(--ink-4)]">{t('hours')}</span>
              </div>
            </Field>

            <Field
              label={t('One-off extra')}
              hint={t('Detergent, fuel, gas, anything you top up between bookings. Leave at zero if there is none.')}
              htmlFor="f-extra"
            >
              <MoneyInput id="f-extra" cents={extraFee} onCents={setExtraFee} suffix={t('per booking')} currency={cur} />
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

        <Field
          label={t('Longer bookings')}
          hint={t('Percent off the hourly price from a day (8 h) and from a week (40 h) of use. 0 to 50.')}
        >
          <div className="flex items-center gap-3">
            <Input
              inputMode="numeric"
              aria-label={t('Day discount, percent')}
              className="tnum"
              value={dayPct}
              onChange={(e) => setDayPct(clampPct(e.target.value))}
            />
            <span className="shrink-0 text-body text-[var(--ink-4)]">{t('% from 8 h')}</span>
            <Input
              inputMode="numeric"
              aria-label={t('Week discount, percent')}
              className="tnum"
              value={weekPct}
              onChange={(e) => setWeekPct(clampPct(e.target.value))}
            />
            <span className="shrink-0 text-body text-[var(--ink-4)]">{t('% from 40 h')}</span>
          </div>
        </Field>

        <Field label={t('Cancellation policy')} hint={policyText(policy)}>
          <Segmented
            label={t('Cancellation policy')}
            options={POLICIES.map((p) => ({ value: p, label: policyName(p) }))}
            value={policy}
            onChange={setPolicy}
          />
          {policy !== 'flexible' && (
            <p className="t-sm mt-2 text-[var(--ink-3)]">
              {t('Moderate and strict apply once Cappy switches them on; until then every booking can be cancelled for a full refund before it starts.')}
            </p>
          )}
        </Field>

        <label className="flex items-start gap-3 rounded-[var(--radius-control)] border border-[var(--line)] p-4">
          <input
            type="checkbox"
            className="mt-1 h-5 w-5 shrink-0 accent-[var(--ink)]"
            checked={instantBook}
            onChange={(e) => setInstantBook(e.target.checked)}
          />
          <span>
            <span className="block text-body font-semibold text-[var(--ink)]">{t('Instant book')}</span>
            <span className="t-sm block text-[var(--ink-3)]">
              {t('Bookings are confirmed as soon as the card is held, without waiting for you to accept. You can still cancel, with a full refund to the renter.')}
            </span>
          </span>
        </label>

        {was?.availability?.weekly.length ? (
          <Card className="p-4">
            <p className="text-body font-semibold">
              {stopSchedule ? t('The weekly schedule stops when you save') : t('Repeats every week')}
            </p>
            <p className="t-sm tnum mt-1 text-[var(--ink-3)]">
              {stopSchedule
                ? t('The windows it made are removed. Windows you added by date stay.')
                : // A list that ends in an abbreviation ("ven.") gets no second full stop (V5-19).
                  `${sentence(rulesToRows(was.availability.weekly).map(rowLabel).join(' · '))}${t('Cappy keeps the next 8 weeks open for you ({tz}).', { tz: was.availability.timeZone })}`}
            </p>
            <Button size="sm" variant="secondary" className="mt-3" onClick={() => setStopSchedule((v) => !v)}>
              {stopSchedule ? t('Keep the weekly schedule') : t('Stop repeating')}
            </Button>
          </Card>
        ) : null}

        {was && (
          <Field label={t('Windows already listed')} hint={t('Remove any that are no longer free.')}>
            {keptSlots.length === 0 ? (
              <p className="t-sm text-[var(--ink-3)]">{t('None coming up.')}</p>
            ) : (
              <ul className="ruled border-t border-[var(--line)]">
                {(allSlots ? keptSlots : keptSlots.slice(0, 6)).map((s) => (
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
                {!allSlots && keptSlots.length > 6 && (
                  <li className="py-2.5">
                    <Button size="sm" variant="secondary" onClick={() => setAllSlots(true)}>
                      {t('Show all {n}', { n: keptSlots.length })}
                    </Button>
                  </li>
                )}
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
              ...(was ? [{ id: 'none' as const, label: 'No new windows', detail: t('Keep what is listed') }] : []),
              ...AVAILABILITY.map((a) => ({ id: a.id, label: a.label, detail: `${rowLabel(a)} · ${t('every week')}` })),
              { id: 'weekly' as Availability, label: 'Set my own weekly hours', detail: weeklyProblem(weekRows) ?? weekRows.map(rowLabel).join(' · ') },
              { id: 'custom' as Availability, label: 'Pick the dates myself', detail: customSummary(custom) },
            ].map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setAvailability(a.id)}
                aria-pressed={availability === a.id}
                aria-controls={a.id === 'custom' ? 'custom-window' : a.id === 'weekly' ? 'weekly-hours' : undefined}
                aria-expanded={a.id === 'custom' || a.id === 'weekly' ? availability === a.id : undefined}
                className={`flex min-h-[62px] w-full items-center gap-3.5 rounded-[var(--radius-field)] border px-4 text-left transition-colors duration-[var(--dur-short)] ${
                  availability === a.id
                    ? 'border-[var(--ink)] bg-[var(--sunken)]'
                    : 'border-[var(--line-strong)] bg-[var(--surface)] hover:border-[var(--ink-4)]'
                }`}
              >
                <span
                  className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 transition-colors duration-[var(--dur-short)] ${
                    availability === a.id
                      ? 'border-[var(--ink)] bg-[var(--ink)] text-[var(--on-inverse)]'
                      : 'border-[var(--line-strong)]'
                  }`}
                >
                  {availability === a.id && <Icon name="check" size={12} strokeWidth={3.5} />}
                </span>
                <span className="min-w-0">
                  <span className="block text-body font-semibold">{t(a.label)}</span>
                  <span className="tnum block text-label text-[var(--ink-3)]">{a.detail}</span>
                </span>
              </button>
            ))}

            {availability === 'weekly' && (
              <div
                id="weekly-hours"
                className="space-y-4 rounded-[var(--radius-field)] border border-[var(--line-strong)] bg-[var(--surface)] p-4"
              >
                {weekRows.map((row, i) => (
                  <fieldset key={i} className="space-y-2">
                    <legend className="sr-only">{t('Weekly hours {n}', { n: i + 1 })}</legend>
                    <div className="flex flex-wrap gap-1.5">
                      {EVERY_DAY.map((d) => (
                        <Chip
                          key={d}
                          selected={row.days.includes(d)}
                          onClick={() =>
                            setWeekRows((rows) =>
                              rows.map((r, j) =>
                                j === i ? { ...r, days: r.days.includes(d) ? r.days.filter((x) => x !== d) : [...r.days, d] } : r,
                              ),
                            )
                          }
                        >
                          {isoWeekday(d)}
                        </Chip>
                      ))}
                    </div>
                    <div className="flex items-end gap-3">
                      <label className="block flex-1">
                        <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('Free from')}</span>
                        <Input
                          type="time"
                          step={900}
                          value={row.start}
                          className="tnum"
                          onChange={(e) => setWeekRows((rows) => rows.map((r, j) => (j === i ? { ...r, start: e.target.value } : r)))}
                        />
                      </label>
                      <label className="block flex-1">
                        <span className="t-label mb-1.5 block text-[var(--ink-3)]">{t('Until')}</span>
                        <Input
                          type="time"
                          step={900}
                          value={row.end === '24:00' ? '23:59' : row.end}
                          className="tnum"
                          onChange={(e) =>
                            setWeekRows((rows) => rows.map((r, j) => (j === i ? { ...r, end: e.target.value === '23:59' ? '24:00' : e.target.value } : r)))
                          }
                        />
                      </label>
                      {weekRows.length > 1 && (
                        <Button
                          size="sm"
                          variant="quiet"
                          aria-label={t('Remove these hours')}
                          onClick={() => setWeekRows((rows) => rows.filter((_, j) => j !== i))}
                        >
                          {t('Remove')}
                        </Button>
                      )}
                    </div>
                  </fieldset>
                ))}
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setWeekRows((rows) => [...rows, { days: [6, 7], start: '10:00', end: '16:00' }])}
                >
                  {t('Add other hours')}
                </Button>
                <p className="t-sm text-[var(--ink-3)]">
                  {t('Repeats every week in {tz}. Cappy keeps the next 8 weeks open and never overlaps a booking.', {
                    tz: was?.availability?.timeZone ?? deviceTimeZone(),
                  })}
                </p>
              </div>
            )}

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
                <p className="tnum text-label text-[var(--ink-3)]">
                  {customProblem(custom)
                    ? t('Each day in the range gets one idle window at those hours.')
                    : t('{days}, {first} to {last}, free {start} – {end} each day.', {
                        days: plural(customDayCount(custom), '{n} day', '{n} days'),
                        first: `${weekday(parseDay(custom.from)!)} ${shortDate(parseDay(custom.from)!)}`,
                        last: `${weekday(parseDay(custom.until)!)} ${shortDate(parseDay(custom.until)!)}`,
                        start: clockTime(custom.start),
                        end: clockTime(custom.end),
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
          <p className="t-plate tnum text-headline leading-[2.625rem] text-[var(--ink)]">
            {formatMoney(
              Math.round((rate * (isBatch ? 4 : minHours) + (isBatch ? setupFee : extraFee)) * 0.85),
              cur,
            )}
          </p>
          <p className="t-sm mt-1.5 text-[var(--ink-2)]">
            {/* Plural and percent in the reader's language: never "de 1 heures", "15 %" in English (V5-17). */}
            {isBatch
              ? t('for a four-hour run, after the {pct} Cappy fee.', { pct: percent(0.15) })
              : t('for a booking of {duration}, after the {pct} Cappy fee.', { duration: durationLabel(minHours), pct: percent(0.15) })}
          </p>
        </Card>

        <Banner
          tone="warn"
          title={t('Paid through Cappy')}
          body={
            instantBook
              ? t('Buyers pay by card when they book: instant book confirms at once. Your share goes to your bank once the booking is done; set up payouts under Earn.')
              : t('Buyers pay by card when you accept. Your share goes to your bank once the booking is done; set up payouts under Earn.')
          }
        />
      </div>
    </Screen>
  )
}
