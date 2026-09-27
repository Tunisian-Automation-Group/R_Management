/**
 * A figure whose digits roll to their new value (VD-17): prices and counts
 * that change under the reader's finger. Keyed from the right, so "€9.00" to
 * "€12.00" rolls the units rather than re-drawing every digit. Screen readers
 * get the plain value once.
 */
export function Odometer({ value }: { value: string }) {
  const chars = [...value]
  return (
    <span className="odo">
      <span className="sr-only">{value}</span>
      {chars.map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={chars.length - i} className="odo-d" aria-hidden="true">
            <span style={{ transform: `translateY(-${Number(ch) * 10}%)` }}>
              {'0123456789'.split('').map((d) => (
                <span key={d}>{d}</span>
              ))}
            </span>
          </span>
        ) : (
          <span key={chars.length - i} aria-hidden="true">
            {ch}
          </span>
        ),
      )}
    </span>
  )
}
