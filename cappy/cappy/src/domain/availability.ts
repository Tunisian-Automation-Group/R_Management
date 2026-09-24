import type { Iso, Slot } from './types.ts'

/** A concrete bookable window, not the whole idle gap, the bit you would take. */
export type Offer = { slotId: string; start: Iso; end: Iso }

const MINUTE = 60_000
const HOUR = 3_600_000

/** Short bookings are offered on the half hour; long ones daily. Offering a
 *  week-long storage booking in 30-minute increments would be useless noise. */
function stepMs(hours: number): number {
  if (hours <= 12) return 30 * MINUTE
  if (hours <= 48) return 3 * HOUR
  return 24 * HOUR
}

const alignUp = (ms: number, step: number) => Math.ceil(ms / step) * step

/**
 * Every start time at which `hours` of work fits inside one of these idle windows,
 * between `from` and `until`.
 *
 * Pure and deterministic: no clock is read, `from` is passed in.
 */
export function offersFor(
  slots: Slot[],
  hours: number,
  from: Iso,
  until: Iso,
  limit = 60,
): Offer[] {
  const fromMs = Date.parse(from)
  const untilMs = Date.parse(until)
  const durationMs = Math.ceil(hours * HOUR)
  const step = stepMs(hours)
  const out: Offer[] = []

  const ordered = [...slots].sort((a, b) => Date.parse(a.start) - Date.parse(b.start))

  for (const slot of ordered) {
    // A 3-day factory gap is not 72 usable machine-hours; respect the real figure.
    if (hours > slot.hoursUsable) continue

    const slotStart = Date.parse(slot.start)
    const slotEnd = Date.parse(slot.end)

    const first = alignUp(Math.max(slotStart, fromMs), step)
    const lastStart = Math.min(slotEnd, untilMs) - durationMs

    for (let t = first; t <= lastStart; t += step) {
      out.push({
        slotId: slot.id,
        start: new Date(t).toISOString(),
        end: new Date(t + durationMs).toISOString(),
      })
      if (out.length >= limit) return out
    }
  }

  return out
}

/** The soonest window that works, or null. Used for ranking. */
export function earliestOffer(
  slots: Slot[],
  hours: number,
  from: Iso,
  until: Iso,
): Offer | null {
  return offersFor(slots, hours, from, until, 1)[0] ?? null
}

/** Idle hours across these windows that nobody has bought. */
export const idleHours = (slots: Slot[]): number =>
  slots.reduce((n, s) => n + s.hoursUsable, 0)
