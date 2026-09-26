import type { InputHTMLAttributes } from 'react'
import type { District } from '../../domain/types.ts'
import { Select } from './ui.tsx'

/** Districts grouped by the market they trade in, so Berlin's are together
 *  instead of an A–Z list mixing Berlin, Lisbon and Milan. */
export function DistrictSelect({
  districts,
  ...rest
}: InputHTMLAttributes<HTMLSelectElement> & { districts: Record<string, District> }) {
  const byMetro = new Map<string, District[]>()
  for (const d of Object.values(districts)) byMetro.set(d.metro, [...(byMetro.get(d.metro) ?? []), d])
  // The chosen option is all a closed picker shows: "Flon (Lausanne)", not a bare
  // "Flon" nobody outside Lausanne places (V6-16). Berlin's own districts need no suffix.
  const label = (d: District) => (d.name.includes(d.city) || (d.city === d.metro && byMetro.get(d.metro)!.length > 1) ? d.name : `${d.name} (${d.city})`)
  return (
    <Select {...rest}>
      {[...byMetro.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([metro, names]) => (
          <optgroup key={metro} label={metro}>
            {names
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((d) => (
                <option key={d.name} value={d.name}>
                  {label(d)}
                </option>
              ))}
          </optgroup>
        ))}
    </Select>
  )
}
