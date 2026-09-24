import type { KeyboardEvent } from "react";
import type { District } from "../../domain/types.ts";
import type { CityStat } from "../../domain/browse.ts";
import { formatEur } from "../../domain/money.ts";

export type MapPin = {
  id: string;
  district: string;
  freeNow: boolean;
  /** Spoken for the pin: "Prusa MK4S x3, Kreuzberg, free now". */
  label: string;
};

export type MapLevel = "city" | "europe";

type Props = {
  level: MapLevel;
  onLevel: (level: MapLevel) => void;
  /** City level: what is free soon, plotted on the neighbourhood. */
  pins: MapPin[];
  districts: Record<string, District>;
  /** Home district, the map centres here at city level. */
  home: string;
  /** How far the search reaches, the city view frames exactly that. */
  radiusKm: number;
  /** Europe level: one marker per city, sized by live capacity. */
  cityStats: CityStat[];
  onOpen: (listingId: string) => void;
  onPickCity: (city: string) => void;
  className?: string;
};

// viewBox units. One height for both levels so switching does not jump the page.
const W = 360;
const H = 250;
const CX = W / 2;
const CY = H / 2 + 4;

const KM_PER_LAT = 110.57;
const KM_PER_LNG_AT_EQUATOR = 111.32;
const rad = (d: number) => (d * Math.PI) / 180;

type LatLng = [number, number];

/* ------------------------------------------------------------ city sketches */
// Rough water, from memory of each city rather than a survey, a sketch, not a
// chart. Only the home city's features are drawn.
const CITY_WATER: Record<string, { pts: LatLng[]; km: number }[]> = {
  Berlin: [
    {
      km: 0.55,
      pts: [
        [52.755, 13.236],
        [52.7, 13.22],
        [52.64, 13.2],
        [52.58, 13.22],
        [52.535, 13.205],
        [52.5, 13.19],
        [52.46, 13.18],
        [52.42, 13.17],
        [52.4, 13.06],
        [52.41, 12.9],
        [52.42, 12.7],
        [52.4125, 12.5316],
      ],
    }, // Havel
    {
      km: 0.22,
      pts: [
        [52.535, 13.205],
        [52.527, 13.245],
        [52.517, 13.3],
        [52.519, 13.33],
        [52.523, 13.345],
        [52.523, 13.37],
        [52.519, 13.4],
        [52.513, 13.418],
        [52.507, 13.435],
        [52.501, 13.445],
        [52.495, 13.46],
        [52.49, 13.47],
        [52.475, 13.49],
        [52.46, 13.53],
        [52.445, 13.575],
        [52.44, 13.62],
      ],
    }, // Spree
    {
      km: 0.08,
      pts: [
        [52.506, 13.335],
        [52.503, 13.365],
        [52.498, 13.38],
        [52.494, 13.395],
        [52.492, 13.42],
        [52.494, 13.44],
        [52.503, 13.452],
      ],
    }, // Landwehrkanal
  ],
  Paris: [
    {
      km: 0.2,
      pts: [
        [48.82, 2.41],
        [48.835, 2.385],
        [48.845, 2.365],
        [48.853, 2.35],
        [48.858, 2.33],
        [48.863, 2.31],
        [48.86, 2.29],
        [48.85, 2.27],
        [48.84, 2.25],
        [48.82, 2.23],
        [48.83, 2.21],
        [48.86, 2.19],
      ],
    }, // Seine
  ],
  Amsterdam: [
    {
      km: 0.5,
      pts: [
        [52.39, 4.83],
        [52.385, 4.87],
        [52.382, 4.9],
        [52.378, 4.92],
        [52.37, 4.96],
        [52.36, 5.0],
      ],
    }, // IJ
    {
      km: 0.1,
      pts: [
        [52.366, 4.9],
        [52.36, 4.903],
        [52.35, 4.905],
        [52.34, 4.91],
        [52.32, 4.92],
      ],
    }, // Amstel
  ],
  Lisbon: [
    {
      km: 1.4,
      pts: [
        [38.68, -9.3],
        [38.69, -9.24],
        [38.695, -9.2],
        [38.7, -9.17],
        [38.705, -9.14],
        [38.71, -9.12],
        [38.72, -9.1],
        [38.74, -9.08],
        [38.77, -9.05],
        [38.8, -9.0],
      ],
    }, // Tejo
  ],
};
// The one loop every local recognises: Berlin's Ringbahn, Paris's Périphérique.
const CITY_RING: Record<string, LatLng[]> = {
  Berlin: [
    [52.549, 13.389],
    [52.55, 13.42],
    [52.53, 13.455],
    [52.503, 13.469],
    [52.494, 13.46],
    [52.475, 13.46],
    [52.469, 13.44],
    [52.467, 13.43],
    [52.47, 13.385],
    [52.475, 13.365],
    [52.479, 13.35],
    [52.478, 13.328],
    [52.48, 13.315],
    [52.49, 13.3],
    [52.497, 13.29],
    [52.501, 13.283],
    [52.507, 13.28],
    [52.518, 13.284],
    [52.53, 13.3],
    [52.534, 13.33],
    [52.536, 13.343],
    [52.543, 13.366],
  ],
  Paris: [
    [48.902, 2.35],
    [48.897, 2.4],
    [48.85, 2.415],
    [48.82, 2.4],
    [48.816, 2.345],
    [48.83, 2.27],
    [48.86, 2.255],
    [48.89, 2.29],
  ],
};
const CITY_LAKES: Record<string, { at: LatLng; rxKm: number; ryKm: number }[]> =
  {
    Berlin: [
      { at: [52.435, 13.175], rxKm: 1.6, ryKm: 3.2 }, // Wannsee
      { at: [52.435, 13.64], rxKm: 3.2, ryKm: 1.5 }, // Müggelsee
      { at: [52.575, 13.245], rxKm: 1.3, ryKm: 2.4 }, // Tegeler See
    ],
  };
const NICE_RINGS = [1, 2, 3, 5, 10, 15, 20, 30, 50, 90];

/* ---------------------------------------------------------- europe sketch */
// Coastlines as open strokes, a sketch of the continent, enough to place a city.
const COAST: LatLng[][] = [
  // Atlantic Iberia → Mediterranean → Italy → Adriatic
  [
    [43.4, -8.4],
    [42.9, -9.3],
    [41.15, -8.7],
    [39.4, -9.4],
    [38.7, -9.4],
    [38.5, -8.9],
    [37.0, -9.0],
    [36.9, -7.9],
    [37.2, -7.4],
    [36.5, -6.3],
    [36.0, -5.6],
    [36.7, -4.4],
    [36.8, -2.5],
    [37.6, -1.0],
    [38.35, -0.5],
    [39.5, -0.3],
    [40.5, 0.5],
    [41.1, 1.25],
    [41.4, 2.2],
    [42.3, 3.3],
    [43.1, 3.1],
    [43.3, 5.4],
    [43.1, 6.1],
    [43.7, 7.3],
    [44.4, 8.9],
    [43.8, 10.3],
    [42.4, 11.2],
    [41.9, 12.2],
    [40.8, 14.2],
    [40.0, 15.3],
    [38.9, 16.1],
    [38.1, 15.65],
    [37.9, 16.1],
    [38.7, 16.6],
    [39.7, 16.5],
    [40.5, 17.2],
    [40.4, 17.9],
    [39.8, 18.4],
    [40.6, 18.0],
    [41.1, 16.9],
    [42.3, 14.6],
    [43.6, 13.5],
    [44.4, 12.3],
    [45.4, 12.3],
    [45.7, 13.7],
    [45.3, 14.4],
    [44.5, 15.0],
    [43.5, 16.4],
    [42.6, 18.1],
  ],
  // Biscay → Channel → North Sea → Baltic
  [
    [43.4, -8.4],
    [43.5, -5.7],
    [43.5, -3.8],
    [43.4, -1.8],
    [43.5, -1.5],
    [44.6, -1.25],
    [46.2, -1.2],
    [47.2, -2.2],
    [47.7, -3.4],
    [48.4, -4.8],
    [48.7, -3.9],
    [48.65, -2.0],
    [49.65, -1.6],
    [49.4, -0.2],
    [49.5, 0.1],
    [50.1, 1.5],
    [50.95, 1.85],
    [51.05, 2.4],
    [51.2, 2.9],
    [51.9, 4.0],
    [52.5, 4.6],
    [52.95, 4.75],
    [53.4, 5.5],
    [53.4, 6.9],
    [53.6, 8.1],
    [53.5, 8.6],
    [53.9, 8.9],
    [54.3, 8.6],
    [55.5, 8.4],
    [56.6, 8.2],
    [57.4, 9.9],
    [57.7, 10.6],
    [56.8, 10.3],
    [56.2, 10.6],
    [55.5, 9.8],
    [54.9, 9.9],
    [54.3, 10.2],
    [54.0, 10.9],
    [54.2, 12.1],
    [54.4, 13.2],
    [54.0, 14.0],
    [53.9, 14.3],
    [54.2, 15.6],
    [54.6, 17.0],
    [54.4, 18.6],
    [54.7, 19.5],
    [55.7, 21.1],
  ],
  // Norway and Sweden, south coasts
  [
    [58.0, 7.0],
    [58.2, 6.0],
    [59.0, 5.7],
    [60.4, 5.3],
  ],
  [
    [58.9, 9.4],
    [59.9, 10.7],
    [58.7, 11.2],
    [57.7, 11.9],
    [56.7, 12.6],
    [56.0, 12.7],
    [55.4, 13.0],
    [55.6, 14.3],
    [56.2, 15.6],
    [56.7, 16.4],
    [57.7, 16.7],
    [58.6, 17.0],
    [59.3, 18.1],
  ],
  // Great Britain
  [
    [51.1, 1.35],
    [51.5, 0.6],
    [51.9, 1.3],
    [52.6, 1.7],
    [52.95, 0.6],
    [53.6, 0.1],
    [54.1, -0.2],
    [54.6, -1.2],
    [55.0, -1.5],
    [55.8, -2.0],
    [56.0, -3.0],
    [56.4, -2.9],
    [57.1, -2.1],
    [57.7, -4.0],
    [58.6, -3.0],
    [58.6, -5.0],
    [57.6, -5.8],
    [56.7, -6.2],
    [56.4, -5.5],
    [55.9, -5.7],
    [55.0, -5.1],
    [54.9, -3.4],
    [54.1, -3.2],
    [53.4, -3.0],
    [53.3, -4.6],
    [52.6, -4.1],
    [51.7, -5.2],
    [51.55, -3.9],
    [51.5, -2.7],
    [51.2, -4.0],
    [50.1, -5.7],
    [50.35, -4.1],
    [50.7, -3.4],
    [50.7, -1.9],
    [50.8, -1.1],
    [50.8, 0.0],
    [50.9, 0.8],
    [51.1, 1.35],
  ],
  // Ireland
  [
    [53.35, -6.2],
    [54.0, -6.3],
    [54.6, -5.9],
    [55.2, -6.2],
    [55.3, -7.3],
    [55.0, -8.4],
    [54.3, -8.6],
    [54.0, -10.1],
    [53.3, -9.1],
    [52.7, -9.5],
    [52.1, -10.4],
    [51.6, -9.5],
    [51.85, -8.3],
    [52.2, -7.0],
    [52.3, -6.4],
    [53.35, -6.2],
  ],
  // Sicily, Sardinia, Corsica
  [
    [38.1, 13.3],
    [38.2, 15.6],
    [37.1, 15.3],
    [36.7, 15.1],
    [37.5, 12.6],
    [38.1, 13.3],
  ],
  [
    [41.2, 9.4],
    [39.2, 9.6],
    [38.9, 8.6],
    [40.6, 8.2],
    [41.2, 9.4],
  ],
  [
    [43.0, 9.4],
    [41.4, 9.2],
    [41.9, 8.6],
    [42.7, 8.9],
    [43.0, 9.4],
  ],
];
// Framed on the footprint, Lisbon to Oranienburg, with enough coast around it
// to read as Europe.
const EUROPE_CENTRE: LatLng = [46.2, 3.0];
const EUROPE_LAT_SPAN = 19; // degrees shown top to bottom

type Rect = { x: number; y: number; w: number; h: number };
const overlaps = (a: Rect, b: Rect) =>
  a.x < b.x + b.w + 4 &&
  b.x < a.x + a.w + 4 &&
  a.y < b.y + b.h + 2 &&
  b.y < a.y + a.h + 2;

/** First free spot for a label around a marker: right, left, below, above, or none. */
function placeLabel(
  at: { x: number; y: number },
  r: number,
  w: number,
  h: number,
  taken: Rect[],
): Rect | null {
  const tries: Rect[] = [
    { x: at.x + r + 6, y: at.y - h / 2, w, h },
    { x: at.x - r - 6 - w, y: at.y - h / 2, w, h },
    { x: at.x - w / 2, y: at.y + r + 4, w, h },
    { x: at.x - w / 2, y: at.y - r - 4 - h, w, h },
  ];
  return (
    tries.find(
      (t) =>
        t.x >= 2 &&
        t.x + w <= W - 2 &&
        t.y >= 2 &&
        t.y + h <= H - 2 &&
        !taken.some((q) => overlaps(q, t)),
    ) ?? null
  );
}

export function CapacityMap({
  level,
  onLevel,
  pins,
  districts,
  home,
  radiusKm,
  cityStats,
  onOpen,
  onPickCity,
  className = "",
}: Props) {
  const origin = districts[home];
  if (!origin) return null;
  // The market, not the town: Potsdam's map is Berlin's map.
  const city = origin.metro;

  const keyOpen = (fn: () => void) => (e: KeyboardEvent<SVGGElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };

  const levelBtn = (l: MapLevel, label: string) => (
    <button
      key={l}
      type="button"
      onClick={() => onLevel(l)}
      aria-pressed={level === l}
      className={`tap min-h-[30px] rounded-[var(--radius-control)] px-2.5 text-[12px] font-semibold transition-colors duration-[160ms]
        ${level === l ? "bg-[var(--inverse)] text-[var(--on-inverse)]" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}
    >
      {label}
    </button>
  );

  return (
    <div className={className}>
      <div className="relative overflow-hidden rounded-[var(--radius-plate)] border border-[var(--line)] bg-[var(--map-ground)]">
        {level === "city" ? (
          <CityView
            pins={pins}
            districts={districts}
            origin={origin}
            radiusKm={radiusKm}
            onOpen={onOpen}
            keyOpen={keyOpen}
          />
        ) : (
          <EuropeView
            cityStats={cityStats}
            districts={districts}
            home={city}
            onPick={(c) => {
              onPickCity(c);
              onLevel("city");
            }}
            keyOpen={keyOpen}
          />
        )}

        <div
          role="group"
          aria-label="Map level"
          className="veil absolute bottom-3 right-3 flex gap-0.5 rounded-[var(--radius-control)] border border-[var(--line)] p-1"
        >
          {levelBtn("city", city)}
          {levelBtn("europe", "Europe")}
        </div>

        {level === "city" && (
          <div className="veil pointer-events-none absolute bottom-3 left-3 flex items-center gap-3 rounded-[var(--radius-control)] border border-[var(--line)] px-2.5 py-1.5 text-[11.5px] font-semibold text-[var(--ink-2)]">
            <span className="inline-flex items-center gap-1.5">
              <span className="relative grid h-2.5 w-2.5 place-items-center">
                <span className="pulse-ring absolute inset-0 rounded-full bg-[var(--sky)]" />
                <span className="relative h-2 w-2 rounded-full bg-[var(--sky)]" />
              </span>
              Free now
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
              Later today
            </span>
          </div>
        )}
      </div>
      {level === "europe" && (
        <p className="t-sm mt-3 px-1 text-[var(--ink-4)]">
          Each market is drawn by its idle hours this week; the figure is what
          they are worth.
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- city view */

function CityView({
  pins,
  districts,
  origin,
  radiusKm,
  onOpen,
  keyOpen,
}: {
  pins: MapPin[];
  districts: Record<string, District>;
  origin: District;
  radiusKm: number;
  onOpen: (id: string) => void;
  keyOpen: (fn: () => void) => (e: KeyboardEvent<SVGGElement>) => void;
}) {
  // Equirectangular around home, fine at city scale.
  const scale = CX / (radiusKm * 1.08); // units per km
  const kmPerLng = KM_PER_LNG_AT_EQUATOR * Math.cos(rad(origin.lat));
  const project = (lat: number, lng: number) => ({
    x: CX + (lng - origin.lng) * kmPerLng * scale,
    y: CY - (lat - origin.lat) * KM_PER_LAT * scale,
  });
  const path = (pts: LatLng[], close = false) =>
    pts
      .map(
        ([la, ln], i) =>
          `${i ? "L" : "M"}${project(la, ln).x.toFixed(1)} ${project(la, ln).y.toFixed(1)}`,
      )
      .join(" ") + (close ? " Z" : "");

  const rings = NICE_RINGS.filter((r) => r <= radiusKm).slice(-3);
  const nearView = radiusKm <= 40;
  const water = CITY_WATER[origin.metro] ?? [];
  const ring = CITY_RING[origin.metro];
  const lakes = CITY_LAKES[origin.metro] ?? [];

  // Every pin in a district shares one coordinate. Spread them on a small ring
  // so three things in Neukölln are three dots, not one; home counts as taken.
  // ponytail: greedy spiral, fine for tens of pins; cluster into a count badge if it ever gets to hundreds.
  const homeAt = project(origin.lat, origin.lng);
  const placed: { x: number; y: number }[] = [homeAt];
  const laid = pins.flatMap((p) => {
    const d = districts[p.district];
    if (!d) return [];
    const base = project(d.lat, d.lng);
    const candidates = [base];
    for (const r of [12, 24, 36]) {
      for (let k = 0; k < 8; k++) {
        const a = (k / 8) * Math.PI * 2 + r / 10;
        candidates.push({
          x: base.x + Math.cos(a) * r,
          y: base.y + Math.sin(a) * r,
        });
      }
    }
    const spot =
      candidates.find((c) =>
        placed.every((q) => Math.hypot(q.x - c.x, q.y - c.y) >= 11),
      ) ?? base;
    placed.push(spot);
    return [{ ...p, ...spot }];
  });

  // Label districts that have something on them. Home first so it always wins
  // its spot, then nearest out, so the crowded centre is labelled before the edge.
  const labelled: { x: number; y: number; w: number }[] = [];
  const labels = Object.values(districts)
    .filter(
      (d) => d.name === origin.name || pins.some((p) => p.district === d.name),
    )
    .map((d) => ({ d, at: project(d.lat, d.lng) }))
    .sort((a, b) =>
      a.d.name === origin.name
        ? -1
        : b.d.name === origin.name
          ? 1
          : Math.hypot(a.at.x - CX, a.at.y - CY) -
            Math.hypot(b.at.x - CX, b.at.y - CY),
    )
    .flatMap(({ d, at }) => {
      const w = d.name.length * 5.6; // ~0.56em per glyph at 10px
      if (at.x < 8 || at.x + 10 + w > W - 4 || at.y < 10 || at.y > H - 6)
        return [];
      const clash = labelled.some(
        (q) =>
          Math.abs(q.y - at.y) < 13 &&
          at.x + 10 < q.x + 10 + q.w + 6 &&
          q.x + 10 < at.x + 10 + w + 6,
      );
      if (clash) return [];
      labelled.push({ ...at, w });
      return [{ name: d.name, ...at }];
    });

  const freeNow = pins.filter((p) => p.freeNow).length;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="anim-fade block h-auto w-full select-none"
      role="img"
      aria-label={`Map of ${pins.length} idle listings within ${radiusKm} km of ${origin.name}, ${freeNow} free right now`}
    >
      {/* distance rings, what "2.3 km" looks like */}
      {rings.map((r) => (
        <g key={r}>
          <circle
            cx={CX}
            cy={CY}
            r={r * scale}
            fill="none"
            stroke="var(--map-line)"
            strokeWidth="1"
            strokeDasharray="3 4"
            className="transition-[r] duration-[420ms] ease-[cubic-bezier(0.2,0,0,1)]"
          />
          {/* A ring that sits under the pin cluster does not get a label. */}
          {r * scale >= 60 && (
            <text
              x={CX - r * scale + 5}
              y={CY - 4}
              fontSize="9.5"
              fontWeight="600"
              fill="var(--map-label)"
              className="tnum"
            >
              {r} km
            </text>
          )}
        </g>
      ))}

      <g
        fill="none"
        stroke="var(--map-water)"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {water.map((wtr, i) => (
          <path
            key={i}
            d={path(wtr.pts)}
            strokeWidth={Math.max(1.4, wtr.km * scale)}
          />
        ))}
      </g>
      <g fill="var(--map-water)">
        {lakes.map((l, i) => {
          const c = project(l.at[0], l.at[1]);
          return (
            <ellipse
              key={i}
              cx={c.x}
              cy={c.y}
              rx={l.rxKm * scale}
              ry={l.ryKm * scale}
            />
          );
        })}
      </g>
      {nearView && ring && (
        <path
          d={path(ring, true)}
          fill="none"
          stroke="var(--map-line)"
          strokeWidth="1.4"
          strokeDasharray="1 3"
          strokeLinecap="round"
        />
      )}

      {labels.map((l) => (
        <text
          key={l.name}
          x={l.x + 10}
          y={l.y + 3.5}
          fontSize="10"
          fontWeight="600"
          fill="var(--map-label)"
          className="pointer-events-none"
        >
          {l.name}
        </text>
      ))}

      {/* you */}
      <g style={{ transform: `translate(${homeAt.x}px, ${homeAt.y}px)` }}>
        <circle r="9" fill="none" stroke="var(--ink)" strokeWidth="2" />
        <circle r="3" fill="var(--ink)" />
      </g>

      {laid.map((p, i) => (
        <g
          key={p.id}
          role="button"
          tabIndex={0}
          aria-label={p.label}
          onClick={() => onOpen(p.id)}
          onKeyDown={keyOpen(() => onOpen(p.id))}
          className="group cursor-pointer outline-none transition-transform duration-[420ms] ease-[cubic-bezier(0.2,0,0,1)]"
          style={{
            transform: `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`,
          }}
        >
          {/* 44px hit area at phone width */}
          <circle r="21" fill="transparent" />
          <g
            className="anim-pop"
            style={{
              transformBox: "fill-box",
              transformOrigin: "center",
              animationDelay: `${120 + i * 40}ms`,
            }}
          >
            {p.freeNow && (
              <circle r="7" fill="var(--sky)" className="pulse-ring" />
            )}
            <circle
              r="10"
              fill="none"
              stroke="var(--focus)"
              strokeWidth="2"
              className="opacity-0 group-focus-visible:opacity-100"
            />
            <circle
              r={p.freeNow ? 6 : 5}
              fill={p.freeNow ? "var(--sky)" : "var(--accent)"}
              stroke="var(--surface)"
              strokeWidth="2"
              className="transition-transform duration-[160ms] group-hover:scale-125 group-active:scale-95"
              style={{ transformBox: "fill-box", transformOrigin: "center" }}
            />
          </g>
        </g>
      ))}
    </svg>
  );
}

/* ------------------------------------------------------------ europe view */

function EuropeView({
  cityStats,
  districts,
  home,
  onPick,
  keyOpen,
}: {
  cityStats: CityStat[];
  districts: Record<string, District>;
  home: string;
  onPick: (city: string) => void;
  keyOpen: (fn: () => void) => (e: KeyboardEvent<SVGGElement>) => void;
}) {
  const scale = H / (EUROPE_LAT_SPAN * KM_PER_LAT); // units per km
  const kmPerLng = KM_PER_LNG_AT_EQUATOR * Math.cos(rad(EUROPE_CENTRE[0]));
  const project = (lat: number, lng: number) => ({
    x: CX + (lng - EUROPE_CENTRE[1]) * kmPerLng * scale,
    y: CY - (lat - EUROPE_CENTRE[0]) * KM_PER_LAT * scale,
  });
  const path = (pts: LatLng[]) =>
    pts
      .map(
        ([la, ln], i) =>
          `${i ? "L" : "M"}${project(la, ln).x.toFixed(1)} ${project(la, ln).y.toFixed(1)}`,
      )
      .join(" ");

  // Cities on the platform with nothing live yet still get a quiet mark, so the
  // footprint reads honestly: five cities, one of them busy.
  const quiet = [...new Set(Object.values(districts).map((d) => d.metro))]
    .filter((c) => !cityStats.some((s) => s.city === c))
    .map((c) => {
      const ds = Object.values(districts).filter((d) => d.metro === c);
      return {
        city: c,
        lat: ds.reduce((n, d) => n + d.lat, 0) / ds.length,
        lng: ds.reduce((n, d) => n + d.lng, 0) / ds.length,
      };
    });

  // Area is hours, so Berlin's volume shows; the label is money, so a small
  // machining valley with a big number is not lost next to it.
  const peak = Math.max(1, ...cityStats.map((c) => c.idle.hours));
  const radiusFor = (hours: number) => 5 + Math.sqrt(hours / peak) * 15;
  // Labels keep clear of every bubble and of each other; busiest cities label first.
  const sized = cityStats.map((c) => ({
    c,
    at: project(c.lat, c.lng),
    r: radiusFor(c.idle.hours),
  }));
  const taken: Rect[] = sized.map(({ at, r }) => ({
    x: at.x - r,
    y: at.y - r,
    w: 2 * r,
    h: 2 * r,
  }));
  const bubbles = sized.map(({ c, at, r }) => {
    const money = formatEur(Math.round(c.idle.value / 100) * 100);
    const w = Math.max(c.city.length * 6, money.length * 5.4);
    const label = placeLabel(at, r, w, 22, taken);
    if (label) taken.push(label);
    return { c, at, r, money, label };
  });

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="anim-fade block h-auto w-full select-none"
      role="img"
      aria-label={`Map of Europe with ${cityStats.length} cities offering idle capacity`}
    >
      {/* graticule every 5° */}
      <g
        stroke="var(--map-line)"
        strokeWidth="0.6"
        strokeDasharray="2 5"
        fill="none"
      >
        {[35, 40, 45, 50, 55, 60].map((la) => {
          const y = project(la, 0).y;
          return <line key={la} x1={0} x2={W} y1={y} y2={y} />;
        })}
        {[-10, -5, 0, 5, 10, 15, 20].map((ln) => {
          const x = project(0, ln).x;
          return <line key={ln} x1={x} x2={x} y1={0} y2={H} />;
        })}
      </g>

      <g
        fill="none"
        stroke="var(--map-water)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {COAST.map((c, i) => (
          <path key={i} d={path(c)} />
        ))}
      </g>

      {quiet.map((c) => {
        const at = project(c.lat, c.lng);
        return (
          <g
            key={c.city}
            role="button"
            tabIndex={0}
            aria-label={`${c.city}, nothing live yet`}
            onClick={() => onPick(c.city)}
            onKeyDown={keyOpen(() => onPick(c.city))}
            className="group cursor-pointer outline-none"
          >
            <circle cx={at.x} cy={at.y} r="21" fill="transparent" />
            <circle
              cx={at.x}
              cy={at.y}
              r="4"
              fill="var(--surface)"
              stroke="var(--ink-4)"
              strokeWidth="1.5"
            />
            <text
              x={at.x + 8}
              y={at.y + 3.5}
              fontSize="10"
              fontWeight="600"
              fill="var(--ink-4)"
            >
              {c.city}
            </text>
          </g>
        );
      })}

      {bubbles.map(({ c, at, r, money, label }, i) => {
        const isHome = c.city === home;
        return (
          <g
            key={c.city}
            role="button"
            tabIndex={0}
            aria-label={`${c.city}: ${Math.round(c.idle.hours)} idle hours worth ${money} this week, ${c.idle.freeNowCount} free now`}
            onClick={() => onPick(c.city)}
            onKeyDown={keyOpen(() => onPick(c.city))}
            className="group cursor-pointer outline-none"
          >
            <circle
              cx={at.x}
              cy={at.y}
              r={Math.max(21, r)}
              fill="transparent"
            />
            <g
              className="anim-pop"
              style={{
                transformBox: "fill-box",
                transformOrigin: "center",
                animationDelay: `${100 + i * 50}ms`,
              }}
            >
              <circle
                cx={at.x}
                cy={at.y}
                r={r}
                fill="var(--accent)"
                fillOpacity={isHome ? 1 : 0.72}
                stroke="var(--surface)"
                strokeWidth="1.5"
              />
              <circle
                cx={at.x}
                cy={at.y}
                r={r + 5}
                fill="none"
                stroke="var(--focus)"
                strokeWidth="2"
                className="opacity-0 group-focus-visible:opacity-100"
              />
              {isHome && (
                <circle
                  cx={at.x}
                  cy={at.y}
                  r={r + 4}
                  fill="none"
                  stroke="var(--ink)"
                  strokeWidth="1.5"
                />
              )}
            </g>
            {label && (
              <>
                <text
                  x={label.x}
                  y={label.y + 9}
                  fontSize="10"
                  fontWeight="700"
                  fill="var(--ink)"
                  className="pointer-events-none"
                >
                  {c.city}
                </text>
                <text
                  x={label.x}
                  y={label.y + 20}
                  fontSize="9.5"
                  fontWeight="600"
                  fill="var(--map-label)"
                  className="tnum pointer-events-none"
                >
                  {money}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
