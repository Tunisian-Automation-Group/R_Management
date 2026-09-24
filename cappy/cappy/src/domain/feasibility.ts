import type { Listing, Requirement } from './types.ts'
import { isBatch, isWindow } from './types.ts'

export type Feasibility = {
  feasible: boolean
  /** 1 while this is rules-based, a rule is certain. Kept in the shape so a
   *  probabilistic judgment layer can replace the body without touching callers. */
  confidence: number
  reasons: string[]
  blockers: string[]
}

/** Fits allowing 90-degree rotation: sort both descending, compare pairwise. */
const fitsInside = (need: { x: number; y: number; z: number }, box: { x: number; y: number; z: number }) => {
  const n = [need.x, need.y, need.z].sort((a, b) => b - a)
  const b = [box.x, box.y, box.z].sort((a, b) => b - a)
  return n.every((v, i) => v <= b[i])
}

/**
 * Can this listing satisfy this request at all, ignoring time and distance?
 *
 * Every rule here is exactly computable from declared facts, which is why it is
 * rules and not a model. The reasons it returns are shown to the buyer verbatim,
 * an explainable match is worth more than a confident score.
 */
export function assessFeasibility(req: Requirement, listing: Listing): Feasibility {
  const reasons: string[] = []
  const blockers: string[] = []

  if (!listing.active) blockers.push('listing is paused')
  if (listing.category !== req.category) blockers.push('different category')

  if (req.mode === 'window' && isWindow(listing)) {
    if (req.hours < listing.minHours) {
      blockers.push(`minimum booking is ${listing.minHours} h`)
    }
    if (req.hours > listing.maxHours) {
      blockers.push(`maximum booking is ${listing.maxHours} h`)
    }
  } else if (req.mode === 'batch' && isBatch(listing)) {
    if (req.material) {
      // A listing that does not describe materials at all cannot promise one.
      if (listing.materials?.includes(req.material)) reasons.push(`${req.material} in stock`)
      else blockers.push(`does not stock ${req.material}`)
    }
    if (req.dims) {
      if (fitsInside(req.dims, listing.maxDims)) {
        reasons.push(`${req.dims.x}×${req.dims.y}×${req.dims.z} mm fits the envelope`)
      } else {
        blockers.push('part exceeds the build envelope')
      }
    }
    if (req.toleranceMm !== undefined) {
      if (listing.toleranceMm === undefined) blockers.push('does not work to a tolerance')
      else if (listing.toleranceMm <= req.toleranceMm) {
        reasons.push(`holds ±${listing.toleranceMm} mm`)
      } else {
        blockers.push(`only holds ±${listing.toleranceMm} mm`)
      }
    }
  } else {
    blockers.push('different kind of booking')
  }

  return { feasible: blockers.length === 0, confidence: 1, reasons, blockers }
}
