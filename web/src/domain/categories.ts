import type { BookingMode, CategoryGroup, CategoryId } from './types.ts'

export type CategoryMeta = {
  id: CategoryId
  label: string
  group: CategoryGroup
  mode: BookingMode
  /** Icon key resolved in the app layer, domain stays free of JSX. */
  icon: string
  /** Second line on the browse row. Concrete, not a slogan. */
  blurb: string
  /** Window categories: the durations people actually book. */
  quickHours?: number[]
  /** Batch categories: the unit a buyer counts in. */
  unitNoun?: string
}

export type GroupMeta = {
  id: CategoryGroup
  label: string
  /** What this part of the chain is for, in the buyer's words. */
  blurb: string
}

/**
 * Make it, move it, or borrow the kit. Every physical job is some sequence of
 * those three, and a buyer arrives knowing which one they are short of.
 */
export const GROUPS: GroupMeta[] = [
  { id: 'make', label: 'Make', blurb: 'Turn a drawing, a file or a spec into parts' },
  { id: 'move', label: 'Move', blurb: 'Get it across Europe, and hold it on the way' },
  { id: 'equip', label: 'Equip', blurb: 'Borrow the machine instead of buying it' },
]

export const CATEGORIES: CategoryMeta[] = [
  // ------------------------------------------------------------------- make
  {
    id: 'fabrication',
    label: 'Fabrication',
    group: 'make',
    mode: 'batch',
    icon: 'mill',
    blurb: 'Milling, turning, laser, sheet metal and moulding',
    unitNoun: 'parts',
  },
  {
    id: 'additive',
    label: '3D printing',
    group: 'make',
    mode: 'batch',
    icon: 'printer',
    blurb: 'FDM, resin and SLS, from one prototype to a short run',
    unitNoun: 'parts',
  },
  {
    id: 'finishing',
    label: 'Finishing',
    group: 'make',
    mode: 'batch',
    icon: 'spray',
    blurb: 'Anodising, powder coating, plating and heat treatment',
    unitNoun: 'parts',
  },
  {
    id: 'print',
    label: 'Print & signage',
    group: 'make',
    mode: 'batch',
    icon: 'press',
    blurb: 'Large format, garments, labels and engraving',
    unitNoun: 'pieces',
  },

  // ------------------------------------------------------------------- move
  {
    id: 'freight',
    label: 'Freight',
    group: 'move',
    mode: 'batch',
    icon: 'truck',
    blurb: 'Van, pallet and groupage space on runs already going',
    unitNoun: 'pallets',
  },
  {
    id: 'warehousing',
    label: 'Warehousing',
    group: 'move',
    mode: 'window',
    icon: 'pallet',
    blurb: 'Pallet, cold and bonded space by the day',
    quickHours: [24, 168, 720],
  },

  // ------------------------------------------------------------------ equip
  {
    id: 'workshop',
    label: 'Workshop & tools',
    group: 'equip',
    mode: 'window',
    icon: 'drill',
    blurb: 'Benches, saws, welders and extraction',
    quickHours: [2, 4, 8],
  },
  {
    id: 'events',
    label: 'Event & AV',
    group: 'equip',
    mode: 'window',
    icon: 'speaker',
    blurb: 'PA, lighting and stage rigs between gigs',
    quickHours: [8, 24, 48],
  },
  {
    id: 'creator',
    label: 'Creator kit',
    group: 'equip',
    mode: 'window',
    icon: 'camera',
    blurb: 'Bodies, glass, studios and treated rooms',
    quickHours: [8, 24, 72],
  },
]

const BY_ID = new Map(CATEGORIES.map((c) => [c.id, c]))

export const category = (id: CategoryId): CategoryMeta => {
  const found = BY_ID.get(id)
  if (!found) throw new Error(`unknown category: ${id}`)
  return found
}

export const categoriesIn = (group: CategoryGroup): CategoryMeta[] =>
  CATEGORIES.filter((c) => c.group === group)

/** Hours phrased the way people say them, not as a raw number. */
export function durationLabel(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`
  if (hours < 24) return `${+hours.toFixed(1)} ${hours === 1 ? 'hour' : 'hours'}`
  const days = hours / 24
  if (days < 7) return `${+days.toFixed(days % 1 ? 1 : 0)} ${days === 1 ? 'day' : 'days'}`
  const weeks = days / 7
  return `${+weeks.toFixed(weeks % 1 ? 1 : 0)} ${weeks === 1 ? 'week' : 'weeks'}`
}
