// A single hand-drawn icon set on one 24-grid with one stroke weight.
// Drawn rather than pulled from a library, and deliberately not emoji: a
// catalogue that lists a plunge saw next to a 5-axis mill needs both to
// look like they belong to the same product.
//
// Each icon has an optional duotone layer, the one shape that gives it mass,
// so at 28–40px on a coloured tile it reads as an object, not a wireframe.

import type { ReactNode } from 'react'

export type IconName =
  // categories
  | 'mill'
  | 'printer'
  | 'spray'
  | 'press'
  | 'truck'
  | 'pallet'
  | 'drill'
  | 'speaker'
  | 'camera'
  // interface
  | 'search'
  | 'chevron-right'
  | 'chevron-left'
  | 'chevron-down'
  | 'close'
  | 'check'
  | 'star'
  | 'clock'
  | 'pin'
  | 'locate'
  | 'calendar'
  | 'plus'
  | 'home'
  | 'ticket'
  | 'wallet'
  | 'user'
  | 'sliders'
  | 'shield'
  | 'info'
  | 'alert'
  | 'arrow-right'
  | 'euro'
  | 'bolt'
  | 'pause'
  | 'heart'

const shapes: Record<IconName, ReactNode> = {
  drill: (
    <>
      <rect x="3" y="6.5" width="9.5" height="6.5" rx="1.8" />
      <path d="M12.5 9.75h8" />
      <path d="M18 8.4v2.7" />
      <path d="M6.2 13v3.2a2.2 2.2 0 0 0 2.2 2.2h1.3" />
    </>
  ),
  speaker: (
    <>
      <rect x="5" y="2.5" width="14" height="19" rx="3" />
      <circle cx="12" cy="15" r="3.6" />
      <circle cx="12" cy="7.2" r="1.6" />
    </>
  ),
  camera: (
    <>
      <rect x="2.5" y="7" width="19" height="13" rx="3" />
      <circle cx="12" cy="13.5" r="3.9" />
      <path d="M8.8 7V5.6a1.1 1.1 0 0 1 1.1-1.1h4.2a1.1 1.1 0 0 1 1.1 1.1V7" />
    </>
  ),
  mill: (
    <>
      <rect x="2.8" y="17.6" width="18.4" height="3.6" rx="1.3" />
      <rect x="9.2" y="2.8" width="5.6" height="3.4" rx="1.2" />
      <path d="M12 6.2v5.4" />
      <path d="M10.4 11.6h3.2l-1.6 3.4z" />
      <path d="M4.6 17.6V9.4M19.4 17.6V9.4" />
    </>
  ),
  // A gantry over a part that is half built: the layers are the whole point.
  printer: (
    <>
      <rect x="2.8" y="3.2" width="18.4" height="14" rx="2.4" />
      <path d="M2.8 8.2h18.4" />
      <path d="M12 8.2v2.6" />
      <rect x="8.6" y="12.4" width="6.8" height="4.8" rx="0.8" />
      <path d="M6.2 20.8h11.6" />
    </>
  ),
  // A gun and the cloud it lays down.
  spray: (
    <>
      <path d="M4.2 8.4h7.2v5.2H4.2z" />
      <path d="M7.4 13.6v4.2a2.4 2.4 0 0 0 2.4 2.4h1.6" />
      <path d="M11.4 9.6h3.4v2.8h-3.4" />
      <path d="M17.8 6.8v.01M20.4 9.4v.01M17.8 12v.01M20.4 14.6v.01M17.8 17.2v.01" />
    </>
  ),
  // A flatbed with a sheet coming off it.
  press: (
    <>
      <rect x="2.6" y="4" width="18.8" height="6.4" rx="1.6" />
      <path d="M6 10.4v3.2M18 10.4v3.2" />
      <rect x="5.4" y="13.6" width="13.2" height="6.8" rx="1.2" />
      <path d="M8.6 16.8h6.8" />
    </>
  ),
  // Box body plus cab, the silhouette everybody reads as freight.
  truck: (
    <>
      <path d="M2.6 6.4h10.8v9.6H2.6z" />
      <path d="M13.4 9.6h3.8l3.2 3.4v3h-7z" />
      <circle cx="7" cy="18.4" r="2.1" />
      <circle cx="17.2" cy="18.4" r="2.1" />
    </>
  ),
  // Stacked pallets in a rack.
  pallet: (
    <>
      <path d="M2.6 20.4h18.8" />
      <rect x="4.2" y="12.6" width="7" height="5.4" rx="0.7" />
      <rect x="12.8" y="12.6" width="7" height="5.4" rx="0.7" />
      <rect x="8.5" y="5.4" width="7" height="5.4" rx="0.7" />
    </>
  ),

  heart: (
    <path d="M12 20.2s-7.6-4.6-7.6-10.3A4.4 4.4 0 0 1 12 7.2a4.4 4.4 0 0 1 7.6 2.7c0 5.7-7.6 10.3-7.6 10.3z" />
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.8" />
      <path d="M16 16l4.4 4.4" />
    </>
  ),
  'chevron-right': <path d="M9.5 5.5l6.5 6.5-6.5 6.5" />,
  'chevron-left': <path d="M14.5 5.5L8 12l6.5 6.5" />,
  'chevron-down': <path d="M5.5 9.5L12 16l6.5-6.5" />,
  close: <path d="M6.2 6.2l11.6 11.6M17.8 6.2L6.2 17.8" />,
  check: <path d="M4.5 12.4l5 5L19.5 7" />,
  star: <path d="M12 3.4l2.7 5.6 6.1.85-4.45 4.3 1.07 6.05L12 17.35 6.58 20.2l1.07-6.05L3.2 9.85l6.1-.85z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.8" />
      <path d="M12 6.8V12.4l3.4 2" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21.2s6.9-5.6 6.9-11a6.9 6.9 0 1 0-13.8 0c0 5.4 6.9 11 6.9 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  locate: (
    <>
      <path d="M20.5 3.5L4.2 10.4c-.9.4-.8 1.7.2 1.9l6.1 1.4 1.4 6.1c.2 1 1.5 1.1 1.9.2z" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.2" y="5" width="17.6" height="16" rx="2.6" />
      <path d="M3.2 9.8h17.6M8 3v4M16 3v4" />
    </>
  ),
  plus: <path d="M12 5.2v13.6M5.2 12h13.6" />,
  home: (
    <>
      <path d="M3.2 11L12 3.8 20.8 11" />
      <path d="M5.8 9.6V20h12.4V9.6" />
    </>
  ),
  ticket: (
    <>
      <path d="M3.2 8.4V6.6a1.4 1.4 0 0 1 1.4-1.4h14.8a1.4 1.4 0 0 1 1.4 1.4v1.8a3.6 3.6 0 0 0 0 7.2v1.8a1.4 1.4 0 0 1-1.4 1.4H4.6a1.4 1.4 0 0 1-1.4-1.4v-1.8a3.6 3.6 0 0 0 0-7.2z" />
      <path d="M13.4 5.2v2.2M13.4 11v2M13.4 16.6v2.2" />
    </>
  ),
  wallet: (
    <>
      <rect x="2.8" y="5.8" width="18.4" height="12.8" rx="3" />
      <path d="M2.8 10.2h18.4" />
      <circle cx="17.2" cy="14.4" r="1.2" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.9" />
      <path d="M4.8 20.2a7.2 7.2 0 0 1 14.4 0" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7.5h16M4 16.5h16" />
      <circle cx="9.5" cy="7.5" r="2.3" />
      <circle cx="15" cy="16.5" r="2.3" />
    </>
  ),
  shield: <path d="M12 3.2l7.2 2.9v5.2c0 5-3.3 8.5-7.2 10.3-3.9-1.8-7.2-5.3-7.2-10.3V6.1z" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.8" />
      <path d="M12 11v5.4" />
      <circle cx="12" cy="7.9" r=".95" fill="currentColor" stroke="none" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3.6l8.9 15.4a1 1 0 0 1-.87 1.5H3.97a1 1 0 0 1-.87-1.5z" />
      <path d="M12 9.6v4.3" />
      <circle cx="12" cy="17" r=".95" fill="currentColor" stroke="none" />
    </>
  ),
  'arrow-right': <path d="M4.5 12h15M13.4 5.9L19.5 12l-6.1 6.1" />,
  euro: (
    <>
      <path d="M18 6.6a7.2 7.2 0 1 0 0 10.8" />
      <path d="M4.6 10.4h8M4.6 13.6h8" />
    </>
  ),
  bolt: <path d="M13.4 2.8L5.2 13.4h5.6l-.8 7.8 8.2-10.6h-5.6z" />,
  pause: <path d="M9.4 5.5v13M14.6 5.5v13" />,
}

/** The one shape per icon that carries its mass when drawn duotone. */
const mass: Partial<Record<IconName, ReactNode>> = {
  drill: <rect x="3" y="6.5" width="9.5" height="6.5" rx="1.8" />,
  speaker: <circle cx="12" cy="15" r="3.6" />,
  camera: <rect x="2.5" y="7" width="19" height="13" rx="3" />,
  mill: <rect x="2.8" y="17.6" width="18.4" height="3.6" rx="1.3" />,
  printer: <rect x="8.6" y="12.4" width="6.8" height="4.8" rx="0.8" />,
  spray: <path d="M4.2 8.4h7.2v5.2H4.2z" />,
  press: <rect x="2.6" y="4" width="18.8" height="6.4" rx="1.6" />,
  truck: <path d="M2.6 6.4h10.8v9.6H2.6z" />,
  pallet: <rect x="8.5" y="5.4" width="7" height="5.4" rx="0.7" />,
  search: <circle cx="11" cy="11" r="6.8" />,
  clock: <circle cx="12" cy="12" r="8.8" />,
  pin: <path d="M12 21.2s6.9-5.6 6.9-11a6.9 6.9 0 1 0-13.8 0c0 5.4 6.9 11 6.9 11z" />,
  locate: <path d="M20.5 3.5L4.2 10.4c-.9.4-.8 1.7.2 1.9l6.1 1.4 1.4 6.1c.2 1 1.5 1.1 1.9.2z" />,
  calendar: <rect x="3.2" y="5" width="17.6" height="16" rx="2.6" />,
  home: <path d="M5.8 9.6L12 4.5l6.2 5.1V20H5.8z" />,
  ticket: (
    <path d="M3.2 8.4V6.6a1.4 1.4 0 0 1 1.4-1.4h14.8a1.4 1.4 0 0 1 1.4 1.4v1.8a3.6 3.6 0 0 0 0 7.2v1.8a1.4 1.4 0 0 1-1.4 1.4H4.6a1.4 1.4 0 0 1-1.4-1.4v-1.8a3.6 3.6 0 0 0 0-7.2z" />
  ),
  wallet: <rect x="2.8" y="5.8" width="18.4" height="12.8" rx="3" />,
  user: <circle cx="12" cy="8" r="3.9" />,
  shield: <path d="M12 3.2l7.2 2.9v5.2c0 5-3.3 8.5-7.2 10.3-3.9-1.8-7.2-5.3-7.2-10.3V6.1z" />,
  info: <circle cx="12" cy="12" r="8.8" />,
  alert: <path d="M12 3.6l8.9 15.4a1 1 0 0 1-.87 1.5H3.97a1 1 0 0 1-.87-1.5z" />,
  bolt: <path d="M13.4 2.8L5.2 13.4h5.6l-.8 7.8 8.2-10.6h-5.6z" />,
  star: <path d="M12 3.4l2.7 5.6 6.1.85-4.45 4.3 1.07 6.05L12 17.35 6.58 20.2l1.07-6.05L3.2 9.85l6.1-.85z" />,
}

export function Icon({
  name,
  size = 22,
  className = '',
  strokeWidth = 1.8,
  duotone = false,
}: {
  name: IconName
  size?: number
  className?: string
  strokeWidth?: number
  /** Fill the icon's main shape at low opacity, for tiles, covers and tabs. */
  duotone?: boolean
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {duotone && mass[name] && (
        <g fill="currentColor" fillOpacity="0.22" stroke="none">
          {mass[name]}
        </g>
      )}
      {shapes[name]}
    </svg>
  )
}

/** Category icon key -> icon name. Keeps the domain free of view concerns. */
export const categoryIcon = (key: string): IconName => key as IconName
