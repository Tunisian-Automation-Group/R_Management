// Small facts about this device, not this person: has it seen the welcome
// screen, has anyone signed in on it, which tab to land on. localStorage on the
// web; the platform's app storage in a store shell (a web view's localStorage
// can be purged by iOS), mirrored here so reads stay synchronous. `loadDevice`
// runs before the first render decision (auth.ts awaits it).
import { isNative, nativeStore } from '../native.ts'

type Flags = { welcomeSeen?: boolean; signedInBefore?: boolean; pushAsked?: boolean; intent?: 'rent' | 'earn' | 'both' }
const KEY = 'cappy.device.v1'
let flags: Flags = {}

function parse(raw: string | null): Flags {
  try {
    return raw ? (JSON.parse(raw) as Flags) : {}
  } catch {
    return {}
  }
}

export async function loadDevice(): Promise<void> {
  if (isNative) flags = parse(await nativeStore.get(KEY))
  else {
    try {
      flags = parse(localStorage.getItem(KEY))
    } catch {
      flags = {}
    }
  }
}

export const device = (): Flags => flags

export function setDevice(patch: Flags): void {
  flags = { ...flags, ...patch }
  const raw = JSON.stringify(flags)
  if (isNative) void nativeStore.set(KEY, raw)
  else {
    try {
      localStorage.setItem(KEY, raw)
    } catch {
      // Storage blocked: remembered for this visit only.
    }
  }
}

/** Drafts that must outlive a session expiring mid-form (U-10). Same storage. */
const DRAFT = 'cappy.draft.'
export const drafts = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(DRAFT + key)
    } catch {
      return null
    }
  },
  set(key: string, value: string): void {
    try {
      if (value) localStorage.setItem(DRAFT + key, value)
      else localStorage.removeItem(DRAFT + key)
    } catch {
      // Not kept; the form still works.
    }
  },
}

/** On a deliberate sign-out: the next person on this device sees none of it. */
export function clearDrafts(): void {
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith(DRAFT)) localStorage.removeItem(k)
  } catch {
    // Nothing stored.
  }
}
