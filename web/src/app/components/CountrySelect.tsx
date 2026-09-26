import type { InputHTMLAttributes } from 'react'
import { Select } from './ui.tsx'
import { locale } from '../../i18n.ts'

/** "Deutschland", "Schweiz": the platform's own country names. */
export const countryName = (cc: string) => new Intl.DisplayNames([locale()], { type: 'region' }).of(cc) ?? cc

/** The countries Cappy is open in (M-2: live markets only). */
export function CountrySelect({ countries, ...rest }: InputHTMLAttributes<HTMLSelectElement> & { countries: string[] }) {
  return (
    <Select {...rest}>
      {[...countries]
        .sort((a, b) => countryName(a).localeCompare(countryName(b), locale()))
        .map((c) => (
          <option key={c} value={c}>
            {countryName(c)}
          </option>
        ))}
    </Select>
  )
}
