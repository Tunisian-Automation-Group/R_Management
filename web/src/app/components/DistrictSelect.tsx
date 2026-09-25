import type { InputHTMLAttributes } from 'react'
import type { District } from '../../domain/types.ts'
import { Select } from './ui.tsx'

/** Districts grouped by the market they trade in, so Berlin's are together
 *  instead of an A–Z list mixing Berlin, Lisbon and Milan. */
export function DistrictSelect({
  districts,
  ...rest
}: InputHTMLAttributes<HTMLSelectElement> & { districts: Record<string, District> }) {
  const byMetro = new Map<string, string[]>()
  for (const d of Object.values(districts)) byMetro.set(d.metro, [...(byMetro.get(d.metro) ?? []), d.name])
  return (
    <Select {...rest}>
      {[...byMetro.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([metro, names]) => (
          <optgroup key={metro} label={metro}>
            {names.sort().map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </optgroup>
        ))}
    </Select>
  )
}
