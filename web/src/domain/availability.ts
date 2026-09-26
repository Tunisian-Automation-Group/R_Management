import type { Slot } from './types.ts'

/** Idle hours across these windows. */
export const idleHours = (slots: Slot[]): number => slots.reduce((n, s) => n + s.hoursUsable, 0)
