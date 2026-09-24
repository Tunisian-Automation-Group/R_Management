import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Slot } from '../../domain/types.ts'
import { rating } from '../../domain/types.ts'
import { CATEGORIES, GROUPS, categoriesIn, category, durationLabel } from '../../domain/categories.ts'
import { findMatches, sortMatches, type SortKey } from '../../domain/match.ts'
import {
  availableSoon,
  cities,
  searchListings,
  type Spotlight,
} from '../../domain/browse.ts'
import { formatEur } from '../../domain/money.ts'
import { buildRequirement, useCappy, useLookups, useMe } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon, categoryIcon } from '../components/Icon.tsx'
import { ListingCard } from '../components/ListingCard.tsx'
import { Photo, SaveButton, WhenChip } from '../components/Photo.tsx'
import { LocationPicker } from '../components/LocationPicker.tsx'
import { CapacityMap, type MapLevel } from '../components/CapacityMap.tsx'
import { Button, Chip, EmptyState, Sheet, Skeleton } from '../components/ui.tsx'
import { distance, relative, when } from '../format.ts'

// The default has to be one of these or the filter opens with nothing selected.
// 75 km is the Berlin-Brandenburg belt the plan names as the first wedge, which
// is what it takes to reach a machine shop; 10 km is what it takes to reach a saw.
const RADII = [10, 30, 75, 150]
const HORIZONS = [1, 3, 7, 21]
const QUANTITIES = [10, 50, 200, 500]

export function Browse() {
  const nav = useNavigate()
  const { state, send } = useCappy()
  const ME = useMe()
  const { owner, slotsFor } = useLookups()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [showMap, setShowMap] = useState(false)
  const [sort, setSort] = useState<SortKey>('best')
  const [mapLevel, setMapLevel] = useState<MapLevel>('city')
  // Twenty-nine equal tiles is a wall, not a shortlist. Eight, then ask.
  const [allSpots, setAllSpots] = useState(false)

  const { search, world, ready } = state
  const now = useMemo(() => new Date(), [state.search, state.world])
  // Where the user is. Switching city is one field on the search, so the hero,
  // the map and the results all move together.
  const home = search.district
  const here = world.districts[home]
  const pickCity = (metro: string) => {
    const first = Object.values(world.districts).find((d) => d.metro === metro)
    if (first) send({ type: 'SEARCH_CHANGED', patch: { district: first.name } })
  }

  const meta = search.categoryId ? category(search.categoryId) : null

  const matches = useMemo(() => {
    const req = buildRequirement(search, now)
    if (!req) return null
    // You cannot book your own machine, so it does not belong in your results.
    const found = findMatches(req, world, now.toISOString()).filter((m) => m.ownerId !== ME)
    return sortMatches(found, sort)
  }, [search, world, now, sort])

  // What is free within reach in the next day, the rail and the map share it.
  const spotlight = useMemo(
    () =>
      // Your own things are not capacity you can buy.
      availableSoon(world, home, search.maxDistanceKm, now.toISOString(), 24, 99).filter(
        (s) => s.owner.id !== ME,
      ),
    [world, home, search.maxDistanceKm, now],
  )

  // Per-city totals, for the location picker and the Europe map.
  const cityStats = useMemo(() => cities(world, now.toISOString()), [world, now])

  const queryHits = useMemo(
    () =>
      search.query.trim()
        ? searchListings(
            world.listings.filter(
              (l) =>
                l.active &&
                l.ownerId !== ME &&
                // Scope to the city you are standing in. Searching "prusa" in
                // Paris used to return a Berlin printer 1,000 km away.
                world.districts[l.district]?.metro === here?.metro,
            ),
            search.query,
          )
        : [],
    [world.listings, world.districts, search.query, here],
  )

  if (!ready || !here) return <BrowseSkeleton />

  return (
    <Screen wide>
      {/* ------------------------------------------------------------ masthead */}
      <header className="flex items-baseline justify-between gap-3 pb-2 pt-8 md:pt-10">
        <span className="t-h1 md:hidden">Cappy</span>
        <span className="hidden md:block">
          <span className="t-h1">Capacity near you</span>
          <span className="t-lede mt-2 block max-w-[48ch]">
            Someone within reach has a machine, a truck or a room standing idle right
            now. Buy the hours, not the thing.
          </span>
        </span>
        <LocationPicker
          label={here.name === here.city ? here.name : `${here.name}, ${here.city}`}
          current={here.metro}
          cities={cityStats}
          onPick={pickCity}
        />
      </header>

      {/* ------------------------------------------------------------- search */}
      <div
        className="scroll-edge isolate sticky z-20 pb-3 pt-4"
        style={{ top: 'env(safe-area-inset-top)', marginInline: -20, paddingInline: 20 }}
      >
        {/* The field is its own glass pane, the way the kit's search bars are,
            rather than a rule drawn across the page. */}
        <div className="glass relative mx-auto max-w-[620px] rounded-[22px] px-4 py-[11px] shadow-[var(--glass-shadow)] md:max-w-none">
          <Icon
            name="search"
            size={17}
            strokeWidth={2}
            className="pointer-events-none absolute left-4 top-[15px] text-[var(--ink-3)]"
          />
          <input
            type="search"
            value={search.query}
            aria-label="Search listings"
            placeholder="Milling, printing, PA rig, saw"
            onChange={(e) => send({ type: 'SEARCH_CHANGED', patch: { query: e.target.value } })}
            className="h-[26px] w-full border-0 bg-transparent pl-7 text-[16.5px] font-medium text-[var(--ink)]
              outline-none placeholder:font-normal placeholder:text-[var(--ink-4)]"
            style={{ fontVariationSettings: "'wdth' 104" }}
          />
        </div>
      </div>

      <div>
        {search.query.trim() ? (
          /* ---------------------------------- free-text results win over everything */
          queryHits.length === 0 ? (
            <EmptyState
              icon="search"
              title={`Nothing matching “${search.query.trim()}”`}
              body="Try a broader word, or pick a category below."
              action={
                <Button
                  variant="secondary"
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { query: '' } })}
                >
                  Clear search
                </Button>
              }
            />
          ) : (
            <section aria-label="Search results">
              <SectionHead
                title="Results"
                aside={`${queryHits.length} ${queryHits.length === 1 ? 'match' : 'matches'}`}
              />
              <ul className="ruled">
                {queryHits.map((l) => {
                  const o = owner(l.ownerId)!
                  return (
                    <li key={l.id}>
                      <button
                        onClick={() => nav(`/listing/${l.id}`)}
                        className="flex w-full items-center gap-4 py-4 text-left transition-opacity duration-[160ms] hover:opacity-70"
                      >
                        <Photo
                          src={l.photos?.[0]}
                          alt={l.title}
                          slots={slotsFor(l.id)}
                          categoryId={l.category}
                          aspect={1}
                          className="w-[52px] shrink-0 rounded-[var(--radius-plate)]"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px] font-semibold">{l.title}</span>
                          <span className="t-sm block truncate text-[var(--ink-3)]">
                            {o.name}, {l.district}
                          </span>
                        </span>
                        <Icon
                          name="chevron-right"
                          size={18}
                          className="shrink-0 text-[var(--ink-4)]"
                        />
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          )
        ) : !meta ? (
          /* -------------------------------- default: what you need, then what is free */
          <>
            {/* The first thing anyone arriving here knows is what they are short
                of. The category index used to sit under twenty-nine cards and a
                stats band, three screens down; it is now the first row. The full
                grouped index further down stays, for browsing. */}
            <nav aria-label="Categories" className="rail mt-5 pb-1 md:m-0 md:mt-5 md:flex-wrap md:p-0">
              {CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { categoryId: c.id } })}
                  className="inline-flex shrink-0 items-center gap-2 rounded-full border border-[var(--line)]
                    bg-[var(--surface)] px-3.5 py-2 text-[13.5px] font-medium text-[var(--ink-2)]
                    transition-colors duration-[160ms] hover:border-[var(--line-strong)] hover:text-[var(--ink)]"
                >
                  <Icon name={categoryIcon(c.icon)} size={16} strokeWidth={1.7} className="text-[var(--ink-3)]" />
                  {c.label}
                </button>
              ))}
            </nav>

            <SectionHead
              title="Free in the next 24 hours"
              aside={spotlight.length > 0 ? String(spotlight.length) : undefined}
              className="mt-7"
            />
            {spotlight.length === 0 ? (
              <EmptyState
                icon="clock"
                title="Nothing free nearby today"
                body={`No idle capacity within ${search.maxDistanceKm} km today. Widening the radius usually finds something.`}
                action={
                  <Button
                    variant="secondary"
                    onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: 90 } })}
                  >
                    Search the whole region
                  </Button>
                }
              />
            ) : (
              <>
                {/* One thing shown large, then the rest small. A row of equal
                    boxes gives a screen nothing to look at first. */}
                <FeatureCard
                  spot={spotlight[0]}
                  slots={slotsFor(spotlight[0].listing.id)}
                  onOpen={() => nav(`/listing/${spotlight[0].listing.id}`)}
                />
                {spotlight.length > 1 && (
                  <ul className="rail mt-8 pb-2 md:m-0 md:mt-10 md:grid md:grid-cols-4 md:gap-6 md:p-0">
                    {spotlight.slice(1, allSpots ? undefined : 9).map((s) => (
                      <li key={s.listing.id} className="md:w-auto">
                        <SpotCard
                          spot={s}
                          slots={slotsFor(s.listing.id)}
                          onOpen={() => nav(`/listing/${s.listing.id}`)}
                        />
                      </li>
                    ))}
                  </ul>
                )}
                {!allSpots && spotlight.length > 9 && (
                  <div className="mt-6">
                    <Button variant="secondary" onClick={() => setAllSpots(true)}>
                      Show all {spotlight.length} free today
                    </Button>
                  </div>
                )}
              </>
            )}


            <SectionHead title="What do you need?" className="mt-14 md:mt-20" />
            {/* Nine categories read as a wall. Three groups read as a decision:
                are you short of making it, moving it, or the kit to do it with. */}
            <div className="md:grid md:grid-cols-3 md:gap-10">
              {GROUPS.map((g) => (
                <section key={g.id} className="max-md:mt-8 md:mt-2">
                  <h3 className="t-h4">{g.label}</h3>
                  <p className="t-sm mt-1 text-[var(--ink-4)]">{g.blurb}</p>
                  <ul className="ruled mt-3 border-t border-[var(--line)]">
                    {categoriesIn(g.id).map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => send({ type: 'SEARCH_CHANGED', patch: { categoryId: c.id } })}
                    className="group flex w-full items-center gap-3 py-3.5 text-left transition-opacity duration-[160ms] hover:opacity-60"
                  >
                    <Icon
                      name={categoryIcon(c.icon)}
                      size={18}
                      strokeWidth={1.6}
                      className="shrink-0 text-[var(--ink-3)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[15px] font-semibold">{c.label}</span>
                      <span className="t-sm block truncate text-[var(--ink-4)]">{c.blurb}</span>
                    </span>
                    <Icon
                      name="chevron-right"
                      size={16}
                      strokeWidth={1.8}
                      className="shrink-0 text-[var(--ink-4)]"
                    />
                  </button>
                </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </>
        ) : (
          /* ------------------------------ a category is chosen: filters + ranked capacity */
          <>
            <div className="border-t border-[var(--ink)] pt-4">
              <h2 className="t-h2">{meta.label}</h2>
              <p className="t-sm mt-1 text-[var(--ink-3)]">{meta.blurb}</p>
            </div>

            <div className="flex flex-wrap items-center gap-2 pb-4 pt-4">
              <Chip selected onClick={() => send({ type: 'SEARCH_CHANGED', patch: { categoryId: null } })}>
                {meta.label}
                <Icon name="close" size={14} strokeWidth={2.4} />
              </Chip>
              <Chip onClick={() => setFiltersOpen(true)}>
                <Icon name="sliders" size={15} strokeWidth={2} />
                {meta.mode === 'window'
                  ? durationLabel(search.hours)
                  : `${search.quantity} ${meta.unitNoun}`}
                {' · '}
                {search.maxDistanceKm} km
              </Chip>
            </div>

            {matches && matches.length > 0 && (
              <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] py-3">
                <p className="t-sm text-[var(--ink-3)]">
                  <span className="tnum font-semibold text-[var(--ink)]">{matches.length}</span>{' '}
                  bookable{matches.length === 1 ? ' slot' : ' slots'}
                </p>
                <div className="flex items-center gap-2">
                  {/* A map answers "which of these is nearest", which is only a
                      question once there are results, so it lives here, not on
                      the way in. */}
                  <button
                    onClick={() => setShowMap((v) => !v)}
                    aria-pressed={showMap}
                    className={`tap inline-flex min-h-[34px] items-center gap-1.5 rounded-[var(--radius-control)] border px-3 text-[13px] font-medium transition-colors duration-[160ms]
                      ${
                        showMap
                          ? 'border-[var(--field)] bg-[var(--field)] font-semibold text-[var(--on-field)]'
                          : 'border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--ink-4)]'
                      }`}
                  >
                    <Icon name="pin" size={15} strokeWidth={2.1} />
                    {showMap ? 'List' : 'Map'}
                  </button>
                  <label className="relative t-sm text-[var(--ink-3)]">
                    <span className="sr-only">Sort results</span>
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value as SortKey)}
                      className="min-h-[34px] appearance-none rounded-[var(--radius-control)] border border-[var(--line)] bg-transparent pl-3 pr-8 text-[13px] font-medium text-[var(--ink-2)]"
                    >
                      <option value="best">Best match</option>
                      <option value="price">Cheapest</option>
                      <option value="soonest">Soonest</option>
                      <option value="nearest">Nearest</option>
                    </select>
                    <Icon
                      name="chevron-down"
                      size={15}
                      strokeWidth={2.2}
                      className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--ink-4)]"
                    />
                  </label>
                </div>
              </div>
            )}

            {!matches || matches.length === 0 ? (
              <EmptyState
                icon="calendar"
                title="No idle capacity fits that"
                body={
                  meta.mode === 'window'
                    ? `Nobody within ${search.maxDistanceKm} km has ${durationLabel(search.hours)} free in the next ${search.withinDays} days. A shorter booking or a wider radius usually fixes it.`
                    : `No machine within ${search.maxDistanceKm} km can finish ${search.quantity} ${meta.unitNoun} by then. Try a longer lead time or a wider radius.`
                }
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: 90 } })}
                    >
                      Widen to 90 km
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => send({ type: 'SEARCH_CHANGED', patch: { withinDays: 21 } })}
                    >
                      Allow 3 weeks
                    </Button>
                  </div>
                }
              />
            ) : showMap ? (
              <div className="pb-2">
                <CapacityMap
                  level={mapLevel}
                  onLevel={setMapLevel}
                  districts={world.districts}
                  home={home}
                  radiusKm={search.maxDistanceKm}
                  cityStats={cityStats}
                  onOpen={(id) => nav(`/listing/${id}`)}
                  onPickCity={pickCity}
                  pins={spotlight.map((s) => ({
                    id: s.listing.id,
                    district: s.listing.district,
                    freeNow: s.freeNow,
                    label: `${s.listing.title}, ${s.listing.district}, ${s.freeNow ? 'free now' : `free ${relative(s.windowStart)}`}`,
                  }))}
                />
              </div>
            ) : (
              <ul className="ruled border-t border-[var(--line)]">
                {matches.map((m, i) => (
                  <li key={m.listingId}>
                    <ListingCard
                      listing={state.world.listings.find((l) => l.id === m.listingId)!}
                      owner={owner(m.ownerId)!}
                      match={m}
                      slots={slotsFor(m.listingId)}
                      rank={sort === 'best' ? i : undefined}
                      onOpen={() => nav(`/listing/${m.listingId}?slot=${m.slotId}`)}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      <Sheet
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        title="Filters"
        footer={
          <Button block size="lg" onClick={() => setFiltersOpen(false)}>
            Show {matches?.length ?? 0} result{matches?.length === 1 ? '' : 's'}
          </Button>
        }
      >
        <div className="space-y-7 pb-4">
          {meta?.mode === 'window' ? (
            <FilterGroup label="How long do you need it?">
              {(meta.quickHours ?? [1, 2, 4]).map((h) => (
                <Chip
                  key={h}
                  selected={search.hours === h}
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { hours: h } })}
                >
                  {durationLabel(h)}
                </Chip>
              ))}
            </FilterGroup>
          ) : (
            <FilterGroup label={`How many ${meta?.unitNoun ?? 'parts'}?`}>
              {QUANTITIES.map((q) => (
                <Chip
                  key={q}
                  selected={search.quantity === q}
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { quantity: q } })}
                >
                  {q}
                </Chip>
              ))}
            </FilterGroup>
          )}

          <FilterGroup label="How far will you travel?">
            {RADII.map((r) => (
              <Chip
                key={r}
                selected={search.maxDistanceKm === r}
                onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: r } })}
              >
                {r} km
              </Chip>
            ))}
          </FilterGroup>

          <FilterGroup label="Needed within">
            {HORIZONS.map((d) => (
              <Chip
                key={d}
                selected={search.withinDays === d}
                onClick={() => send({ type: 'SEARCH_CHANGED', patch: { withinDays: d } })}
              >
                {d === 1 ? '24 hours' : `${d} days`}
              </Chip>
            ))}
          </FilterGroup>

          {matches && matches.length > 0 && (
            <p className="t-sm text-[var(--ink-4)]">Soonest right now is {when(matches[0].start)}.</p>
          )}
        </div>
      </Sheet>
    </Screen>
  )
}

/* ------------------------------------------------------------------ pieces */

/** A labelled row of chips in the filter sheet. */
function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="t-h4 mb-3">{label}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

/**
 * The lead item. A tall plate at full width with the opening time set across
 * it, and the details below in a single line of small type.
 */
function FeatureCard({
  spot,
  slots,
  onOpen,
}: {
  spot: Spotlight
  slots: Slot[]
  onOpen: () => void
}) {
  return (
    <button
      onClick={onOpen}
      className="group block w-full text-left transition-opacity duration-[200ms] hover:opacity-90
        md:grid md:grid-cols-[1.7fr_1fr] md:items-end md:gap-10"
    >
      <Photo
        src={spot.listing.photos?.[0]}
        alt={spot.listing.title}
        slots={slots}
        categoryId={spot.listing.category}
        aspect={16 / 10}
        priority
        className="w-full rounded-[var(--radius-plate)] shadow-[var(--shadow-plate)]"
      >
        <WhenChip
          start={spot.windowStart}
          state={spot.freeNow ? 'now' : 'later'}
          className="bottom-4 left-4"
        />
        <SaveButton id={spot.listing.id} title={spot.listing.title} className="absolute right-4 top-4" />
      </Photo>
      {/* On a phone this sits under the photograph. On a page it sits beside it. */}
      <span className="mt-5 block md:mt-0 md:pb-2">
        <span className="t-h2 block text-balance">{spot.listing.title}</span>
        <span className="t-sm mt-2 hidden text-[var(--ink-3)] md:block">
          {spot.listing.blurb}
        </span>
        <span className="mt-2.5 flex items-baseline justify-between gap-4 md:mt-5 md:border-t md:border-[var(--line)] md:pt-4">
          <span className="t-sm tnum min-w-0 truncate text-[var(--ink-3)]">
            {spot.listing.district}, {distance(spot.distanceKm)}
          </span>
          <span className="tnum shrink-0 text-[17px] font-semibold md:text-[22px]">
            <span className="mr-1 text-[13px] font-normal text-[var(--ink-4)]">from</span>
            {formatEur(spot.fromPrice)}
          </span>
        </span>
      </span>
    </button>
  )
}

/** One thing that is free soon: what it is, when, and what it costs. */
function SpotCard({
  spot,
  slots,
  onOpen,
}: {
  spot: Spotlight
  slots: Slot[]
  onOpen: () => void
}) {
  return (
    <button
      onClick={onOpen}
      className="group w-[188px] text-left transition-opacity duration-[160ms] hover:opacity-75 md:w-full"
    >
      <Photo
        src={spot.listing.photos?.[0]}
        alt={spot.listing.title}
        slots={slots}
        categoryId={spot.listing.category}
        aspect={4 / 3}
        className="rounded-[var(--radius-plate)]"
      >
        <WhenChip start={spot.windowStart} state={spot.freeNow ? 'now' : 'later'} />
        <SaveButton id={spot.listing.id} title={spot.listing.title} />
      </Photo>
      <span className="block pt-3">
        <span className="line-clamp-2 block min-h-[40px] text-[14.5px] font-semibold leading-[20px]">
          {spot.listing.title}
        </span>
        <span className="mt-1.5 flex items-baseline justify-between gap-2">
          <span className="t-sm tnum min-w-0 truncate text-[var(--ink-4)]">
            {/* Trust at a glance, before anyone opens the listing. */}
            {rating(spot.owner) !== null && (
              <span className="mr-2 font-semibold text-[var(--ink-2)]">
                ★ {rating(spot.owner)!.toFixed(1)}
              </span>
            )}
            {rating(spot.owner) === null && (
              <span className="mr-2 font-semibold text-[var(--ink-2)]">New</span>
            )}
            {distance(spot.distanceKm)}
          </span>
          {/* "5 €" beside "212 €" with no unit could not be compared. This is the
              cheapest real booking, so it is labelled as a floor. */}
          <span className="tnum shrink-0 text-[14.5px] font-semibold">
            <span className="mr-1 text-[12px] font-normal text-[var(--ink-4)]">from</span>
            {formatEur(spot.fromPrice)}
          </span>
        </span>
      </span>
    </button>
  )
}

/** Mirrors the real layout so nothing shifts when data lands. */
function BrowseSkeleton() {
  return (
    <Screen>
      <div className="pt-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-[26px] w-[86px]" />
          <Skeleton className="h-[20px] w-[120px]" />
        </div>
        <Skeleton className="mt-5 h-[34px] w-full" />
        <Skeleton className="mt-4 h-[44px] w-full" />
        <div className="mt-8 flex items-baseline justify-between">
          <Skeleton className="h-[22px] w-[180px]" />
          <Skeleton className="h-[16px] w-[64px]" />
        </div>
        <div className="mt-4 flex gap-3.5 overflow-hidden">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-[248px] w-[152px] shrink-0" />
          ))}
        </div>
      </div>
    </Screen>
  )
}
