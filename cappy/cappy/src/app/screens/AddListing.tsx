import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CategoryId, Listing, Material, Slot } from '../../domain/types.ts'
import { CATEGORIES, category } from '../../domain/categories.ts'
import { formatEur } from '../../domain/money.ts'
import { districts } from '../../data/seed.ts'
import { ME, useCappy } from '../store.tsx'
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
  Select,
  Textarea,
} from '../components/ui.tsx'

const MATERIALS: Material[] = [
  'PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'Resin',
  'Aluminium 6061', 'Stainless 304', 'Steel S235', 'Brass', 'POM', 'Acrylic', 'Plywood',
]

const RULE_SUGGESTIONS = [
  'Back the same day',
  'Leave it as you found it',
  'No smoking',
  'Cash or bank transfer',
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

/** Every day in the range, at the given local hours. */
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

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

const shortDate = (d: Date) => d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

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
  if (!from || !until) return 'Pick a first and a last day.'
  if (until < from) return 'The last day comes before the first.'
  if ((until.getTime() - from.getTime()) / 86_400_000 > MAX_CUSTOM_DAYS) {
    return `Keep it under ${MAX_CUSTOM_DAYS} days. You can add more later.`
  }
  if (start === null || end === null) return 'Pick the hours it is free on those days.'
  if (end <= start) return 'It has to stop being free after it starts being free.'
  if (end - start < 0.5) return 'Give people at least half an hour.'
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

type Errors = Partial<Record<'title' | 'blurb' | 'rate' | 'instructions' | 'machine' | 'availability', string>>

export function AddListing() {
  const nav = useNavigate()
  const { send } = useCappy()

  const [categoryId, setCategoryId] = useState<CategoryId | null>(null)
  const [title, setTitle] = useState('')
  const [blurb, setBlurb] = useState('')
  const [district, setDistrict] = useState('Kreuzberg')
  const [rate, setRate] = useState(400)
  const [extraFee, setExtraFee] = useState(0)
  const [extraLabel, setExtraLabel] = useState('Consumables')
  const [minHours, setMinHours] = useState(1)
  const [maxHours, setMaxHours] = useState(6)
  const [machine, setMachine] = useState('')
  const [materials, setMaterials] = useState<Material[]>([])
  const [unitsPerHour, setUnitsPerHour] = useState(10)
  const [setupFee, setSetupFee] = useState(1500)
  const [availability, setAvailability] = useState<Availability>('evenings')
  const [custom, setCustom] = useState<CustomWindow>(defaultCustom)
  const [instructions, setInstructions] = useState('')
  const [rules, setRules] = useState<string[]>([])
  const [errors, setErrors] = useState<Errors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const meta = categoryId ? category(categoryId) : null
  const isBatch = meta?.mode === 'batch'

  // Validation runs on blur and on submit, never on every keystroke, which
  // shouts at people while they are still typing the first word.
  const validate = (): Errors => {
    const e: Errors = {}
    if (title.trim().length < 3) e.title = 'Give it a name people will recognise.'
    if (blurb.trim().length < 10) e.blurb = 'One line on condition or what it is good for.'
    if (rate <= 0) e.rate = 'Set a price above zero.'
    if (instructions.trim().length < 10) {
      e.instructions = 'Say how someone actually gets hold of it.'
    }
    if (isBatch && machine.trim().length < 2) e.machine = 'Which machine is it?'
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

  const buildSlots = (listingId: string): Slot[] => {
    const out: Slot[] = []

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
          id: `${listingId}_w${d}`,
          listingId,
          start: new Date(first).toISOString(),
          end: new Date(closes).toISOString(),
          // Floored to the quarter hour: usable hours may never exceed the
          // window itself, which is a rule the catalog enforces too.
          hoursUsable: Math.floor(((closes - first) / 3_600_000) * 4) / 4,
        })
      }
      return out
    }

    const preset = AVAILABILITY.find((a) => a.id === availability)!
    const base = new Date()
    base.setHours(0, 0, 0, 0)
    // Two weeks out is enough to look real without pretending to know December.
    for (let d = 0; d < 14; d++) {
      if (!preset.days.includes(d % 7)) continue
      const from = new Date(base.getTime() + d * 86_400_000 + preset.from * 3_600_000)
      const to = new Date(base.getTime() + d * 86_400_000 + preset.to * 3_600_000)
      out.push({
        id: `${listingId}_w${d}`,
        listingId,
        start: from.toISOString(),
        end: to.toISOString(),
        hoursUsable: preset.to - preset.from,
      })
    }
    return out
  }

  const submit = () => {
    const e = validate()
    setErrors(e)
    setTouched({ title: true, blurb: true, rate: true, instructions: true, machine: true, availability: true })
    if (Object.keys(e).length > 0 || !categoryId || !meta) {
      document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
      return
    }

    const id = `own_${Date.now().toString(36)}`
    const shared = {
      id,
      ownerId: ME,
      category: categoryId,
      title: title.trim(),
      blurb: blurb.trim(),
      district,
      instructions: instructions.trim(),
      rules: rules.length ? rules : ['Leave it as you found it'],
      active: true,
    }

    const listing: Listing = isBatch
      ? {
          ...shared,
          mode: 'batch',
          machine: machine.trim(),
          materials: materials.length ? materials : ['PLA'],
          maxDims: { x: 300, y: 300, z: 300 },
          toleranceMm: 0.1,
          unitsPerHour,
          setupHours: 1,
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
          extraLabel: extraFee > 0 ? extraLabel.trim() || 'Consumables' : 'No extras',
        }

    send({ type: 'LISTING_ADDED', listing, slots: buildSlots(id) })
    send({ type: 'TOAST', message: `${listing.title} is live` })
    nav('/earn', { replace: true })
  }

  /* --------------------------------------------- step 1: pick a category */
  if (!categoryId) {
    return (
      <Screen
        back="/earn"
        eyebrow="New listing"
        title="What are you lending?"
        sub="Pick the closest thing. You can be specific on the next screen."
      >
        <ul className="ruled border-t border-[var(--line)]">
          {CATEGORIES.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => {
                  setCategoryId(c.id)
                  setRate(c.mode === 'batch' ? 6000 : 400)
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
      eyebrow="New listing"
      title={`List your ${meta!.label.toLowerCase()}`}
      sub="Four minutes now, and the idle hours start paying."
      footer={
        <Button block size="lg" onClick={submit}>
          Publish listing
        </Button>
      }
    >
      <button
        onClick={() => setCategoryId(null)}
        className="mb-7 inline-flex min-h-[38px] items-center gap-2 rounded-[var(--radius-control)] border border-[var(--line)] px-3.5 text-[13.5px] font-semibold
          transition-colors duration-[160ms] hover:border-[var(--ink-4)]"
      >
        <Icon name={categoryIcon(meta!.icon)} size={17} className="text-[var(--accent-text)]" />
        {meta!.label}
        <Icon name="close" size={14} strokeWidth={2.4} className="text-[var(--ink-4)]" />
      </button>

      <div className="space-y-6">
        <Field label="Name it" error={errorFor('title')} htmlFor="f-title">
          <Input
            id="f-title"
            value={title}
            invalid={Boolean(errorFor('title'))}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={blur('title')}
            placeholder={isBatch ? 'Haas VF-2SS' : 'Festool TS 55 plunge saw'}
          />
        </Field>

        <Field
          label="One line about it"
          hint="What a neighbour would want to know before asking."
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
            placeholder={isBatch ? '3-axis, fast spindle, free most of August.' : '8 kg, quiet, free most evenings.'}
          />
        </Field>

        {isBatch && (
          <>
            <Field label="Machine" error={errorFor('machine')} htmlFor="f-machine">
              <Input
                id="f-machine"
                value={machine}
                invalid={Boolean(errorFor('machine'))}
                onChange={(e) => setMachine(e.target.value)}
                onBlur={blur('machine')}
                placeholder="DMG Mori DMU 50"
              />
            </Field>

            <Field label="Materials you stock" hint="Tap all that apply.">
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
                    {m}
                  </Chip>
                ))}
              </div>
            </Field>

            <Field
              label="Parts per hour"
              hint="Roughly, once it is set up. This is what turns a quantity into a delivery date."
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
          </>
        )}

        <Field label="Where is it?" htmlFor="f-district">
          <Select id="f-district" value={district} onChange={(e) => setDistrict(e.target.value)}>
            {Object.keys(districts).map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Price" error={errorFor('rate')} htmlFor="f-rate">
          <MoneyInput id="f-rate" cents={rate} onCents={setRate} invalid={Boolean(errorFor('rate'))} />
        </Field>

        {isBatch ? (
          <Field label="Setup fee" hint="Charged once per job, for programming and fixturing.">
            <MoneyInput cents={setupFee} onCents={setSetupFee} suffix="per job" />
          </Field>
        ) : (
          <>
            <Field label="Shortest and longest booking">
              <div className="flex items-center gap-3">
                <Input
                  inputMode="numeric"
                  aria-label="Minimum hours"
                  className="tnum"
                  value={minHours}
                  onChange={(e) => setMinHours(Math.max(1, Number(e.target.value) || 1))}
                />
                <span className="shrink-0 text-[14px] text-[var(--ink-4)]">to</span>
                <Input
                  inputMode="numeric"
                  aria-label="Maximum hours"
                  className="tnum"
                  value={maxHours}
                  onChange={(e) => setMaxHours(Math.max(minHours, Number(e.target.value) || minHours))}
                />
                <span className="shrink-0 text-[14px] text-[var(--ink-4)]">hours</span>
              </div>
            </Field>

            <Field
              label="One-off extra"
              hint="Detergent, fuel, gas, anything you top up between bookings. Leave at zero if there is none."
            >
              <MoneyInput cents={extraFee} onCents={setExtraFee} suffix="per booking" />
              {extraFee > 0 && (
                <div className="mt-2">
                  <Input
                    aria-label="What the extra covers"
                    value={extraLabel}
                    onChange={(e) => setExtraLabel(e.target.value)}
                    placeholder="Detergent and softener"
                  />
                </div>
              )}
            </Field>
          </>
        )}

        <Field
          label="When is it free?"
          hint="Pick a pattern, or type the exact dates and hours. You can change any week later."
          error={errorFor('availability')}
        >
          <div className="space-y-2">
            {[
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
                  <span className="block text-[15px] font-semibold">{a.label}</span>
                  <span className="tnum block text-[13px] text-[var(--ink-3)]">{a.detail}</span>
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
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">From</span>
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
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">Until</span>
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
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">Free from</span>
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
                    <span className="t-label mb-1.5 block text-[var(--ink-3)]">Until</span>
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
                    ? 'Each day in the range gets one idle window at those hours.'
                    : `${customDayCount(custom)} ${customDayCount(custom) === 1 ? 'day' : 'days'}, ${
                        WEEKDAYS[(parseDay(custom.from)!.getDay() + 6) % 7]
                      } ${shortDate(parseDay(custom.from)!)} to ${
                        WEEKDAYS[(parseDay(custom.until)!.getDay() + 6) % 7]
                      } ${shortDate(parseDay(custom.until)!)}, free ${custom.start} – ${custom.end} each day.`}
                </p>
              </div>
            )}
          </div>
        </Field>

        <Field
          label="How does someone get it?"
          hint="Only shown after you accept a request."
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
            placeholder="Side entrance, doorbell marked Brandt. Pods are in the glass jar."
          />
        </Field>

        <Field label="House rules" hint="Optional, but they prevent most of the awkward messages.">
          <div className="flex flex-wrap gap-2">
            {RULE_SUGGESTIONS.map((r) => (
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

        <Card className="border-0 bg-[var(--field)] p-5">
          <p className="t-label mb-2" style={{ color: 'var(--on-field-dim)' }}>
            What a booking would earn you
          </p>
          <p className="t-plate tnum text-[38px] leading-[42px]" style={{ color: 'var(--on-field)' }}>
            {formatEur(
              Math.round((rate * (isBatch ? 4 : minHours) + (isBatch ? setupFee : extraFee)) * 0.85),
            )}
          </p>
          <p className="t-sm mt-1.5" style={{ color: 'var(--on-field-dim)' }}>
            for a {isBatch ? 'four-hour run' : `${minHours}-hour booking`}, after the 15% Cappy fee.
          </p>
        </Card>

        <Banner
          tone="warn"
          title="You settle payment directly"
          body="Cappy does not hold money yet. Agree cash or transfer with the person when you hand it over."
        />
      </div>
    </Screen>
  )
}
