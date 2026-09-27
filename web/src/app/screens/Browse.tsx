import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNav } from '../nav.ts'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { rating } from '../../domain/types.ts'
import { CATEGORIES, GROUPS, categoriesIn, category, durationLabel } from '../../domain/categories.ts'
import type { SortKey } from '../../domain/match.ts'
import { formatMoney } from '../../domain/money.ts'
import {
  SEARCH_MIN,
  getListing,
  useCities,
  useDistricts,
  useMatches,
  useMeQuery,
  useSearch,
  useSpotlight,
  type Spotlight,
} from '../../data/repo.ts'
import { buildRequirement, useCappy, useMe } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { Icon, categoryIcon } from '../components/Icon.tsx'
import { CategoryObject } from '../components/Cover.tsx'
import { ListingCard } from '../components/ListingCard.tsx'
import { Photo, PhotoGrid, SaveButton, WhenChip } from '../components/Photo.tsx'
import { LocationPicker } from '../components/LocationPicker.tsx'
import { distanceKm } from '../../domain/match.ts'
import { CapacityMap, type MapLevel } from '../components/CapacityMap.tsx'
import { Banner, Button, Chip, EmptyState, oneDecimal, Sheet, Skeleton, TapLink } from '../components/ui.tsx'
import { dayShort, formatDistance, formatRadius, relative, time, when } from '../format.ts'
import { plural, t } from '../../i18n.ts'

// The default has to be one of these or the filter opens with nothing selected.
// 75 km is the Berlin-Brandenburg belt the plan names as the first wedge, which
// is what it takes to reach a machine shop; 10 km is what it takes to reach a saw.
const RADII = [10, 30, 75, 150]
const HORIZONS = [1, 3, 7, 14, 21]
const SORTS: SortKey[] = ['best', 'price', 'soonest', 'nearest']
const QUANTITIES = [10, 50, 200, 500]

export function Browse() {
  const nav = useNav()
  const { state, send } = useCappy()
  const ME = useMe()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [showMap, setShowMap] = useState(false)
  // The sort is part of the address like the rest of the search.
  const [urlParams, setUrlParams] = useSearchParams()
  const sort: SortKey = SORTS.find((k) => k === urlParams.get('sort')) ?? 'best'
  const setSort = (k: SortKey) => {
    const next = new URLSearchParams(urlParams)
    if (k === 'best') next.delete('sort')
    else next.set('sort', k)
    setUrlParams(next, { replace: true })
  }
  const [mapLevel, setMapLevel] = useState<MapLevel>('city')
  // Twenty-nine equal tiles is a wall, not a shortlist. Eight, then ask.
  const [allSpots, setAllSpots] = useState(false)

  const { search } = state
  useSearchInUrl()
  // To the minute, so the query key (and so the request) is stable between renders.
  const now = useMemo(() => new Date(Math.floor(Date.now() / 60_000) * 60_000), [search])
  const districtsQ = useDistricts()
  const citiesQ = useCities()
  const districts = districtsQ.data ?? {}
  const cityStats = citiesQ.data ?? []
  // Where the user is. Switching city is one field on the search, so the hero,
  // the map and the results all move together.
  const home = search.district
  const here = districts[home]
  // A city starts from the district nearest its centre, not whichever comes
  // first (for Berlin that was Brandenburg, 60 km out).
  const pickCity = (metro: string) => {
    const inCity = Object.values(districts).filter((d) => d.metro === metro)
    const centre = cityStats.find((c) => c.city === metro) ?? inCity[0]
    if (!centre) return
    const best = inCity.reduce<(typeof inCity)[number] | undefined>(
      (a, d) => (!a || distanceKm(centre, d) < distanceKm(centre, a) ? d : a),
      undefined,
    )
    if (best) send({ type: 'SEARCH_CHANGED', patch: { district: best.name, districtChosen: true } })
  }

  const meta = search.categoryId ? category(search.categoryId) : null
  const requirement = useMemo(() => buildRequirement(search, now), [search, now])
  const matchesQ = useMatches(requirement, sort)
  const matches = requirement ? (matchesQ.data ?? null) : null

  // What is free within reach in the next day, the rail and the map share it.
  // Your own things are not capacity you can buy.
  // Wait for the profile's home district (Member moves the search there) unless
  // a place was picked by hand: otherwise Explore asked twice (V4-23).
  const me = useMeQuery()
  const settled = search.districtChosen || (!me.isPending && (!me.data?.homeDistrict || me.data.homeDistrict === home))
  const spotQ = useSpotlight(settled ? home : '', search.maxDistanceKm)
  const spotlight = (spotQ.data ?? []).filter((s) => s.owner.id !== ME)

  // Scoped to the city you are standing in: "prusa" in Paris should not find Berlin.
  const searchQ = useSearch(search.query, here?.metro)
  const queryHits = search.query.trim()
    ? (searchQ.data?.items ?? []).filter((v) => v.listing.active && v.listing.ownerId !== ME)
    : []

  const failed = districtsQ.error ?? spotQ.error ?? matchesQ.error
  if (failed && !here) {
    return (
      <Screen wide>
        <div className="pt-8">
          <Banner
            tone="danger"
            title={t('Cappy is not reachable right now')}
            body={failed.message}
            action={
              <Button size="sm" onClick={() => void Promise.all([districtsQ.refetch(), spotQ.refetch()])}>
                {t('Try again')}
              </Button>
            }
          />
        </div>
      </Screen>
    )
  }

  if (!here) return <BrowseSkeleton />

  return (
    <Screen wide>
      <PhotoGrid>
      {/* ------------------------------------------------------------ masthead
          Content first (owner, 2026-09-27): the brand in one line, where you
          are, and one plain sentence of what this is. The search is the hero
          and the first listings sit above the fold on a 390 px phone. */}
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 pt-3 md:pt-8">
        <span className="t-wordmark md:hidden">Cappy</span>
        <LocationPicker
          label={here.name === here.city ? here.name : `${here.name}, ${here.city}`}
          current={here.metro}
          cities={cityStats}
          onPick={pickCity}
          districts={Object.values(districts)}
          onPickDistrict={(name) => send({ type: 'SEARCH_CHANGED', patch: { district: name, districtChosen: true } })}
        />
      </header>
      <h1 className="t-h2 mt-5 max-w-[20ch] text-balance md:mt-4 md:max-w-none">{t('Rent what you need, by the hour')}</h1>
      {/* ------------------------------------------------------------- search */}
      <div
        className="scroll-edge isolate sticky z-20 pb-3 pt-4"
        style={{ top: 'calc(env(safe-area-inset-top) + 8px)', marginInline: -20, paddingInline: 20 }}
      >
        {/* The field is its own glass pane, the way the kit's search bars are,
            rather than a rule drawn across the page. */}
        <div className="glass-strong relative flex min-h-16 max-w-[720px] items-center rounded-[var(--radius-xl)] px-5 py-2 shadow-[var(--glass-shadow-raised)]">
          <Icon
            name="search"
            size={17}
            strokeWidth={2}
            className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-[var(--ink-2)]"
          />
          <form
            role="search"
            onSubmit={(e) => {
              // Results are live; Enter just puts a touch keyboard away. With a
              // mouse and keyboard, focus stays in the field (V6-20).
              e.preventDefault()
              if (matchMedia('(pointer: coarse)').matches) (document.activeElement as HTMLElement | null)?.blur()
            }}
            className="w-full"
          >
          {/* The prompt and its examples are real text that wraps at any size
              (J-2): an input's placeholder cannot wrap, so it is empty and the
              words sit in the same grid cell, gone as soon as someone types. */}
          <span className="grid pl-8">
            <input
              type="search"
              enterKeyHint="search"
              value={search.query}
              aria-label={t('Search listings')}
              aria-describedby="search-hint"
              placeholder=" "
              onChange={(e) => send({ type: 'SEARCH_CHANGED', patch: { query: e.target.value } })}
              className="peer col-start-1 row-start-1 min-h-[1.5em] w-full self-center border-0 bg-transparent text-body-l font-semibold text-[var(--ink)] outline-none"
            />
            <span
              id="search-hint"
              aria-hidden="true"
              className="pointer-events-none col-start-1 row-start-1 peer-[:not(:placeholder-shown)]:invisible"
            >
              <span className="block text-body-l font-semibold text-[var(--ink)]">{t('What do you need?')}</span>
              <span className="block text-label text-[var(--ink-3)]">{t('Drill, van, 3D printer, studio…')}</span>
            </span>
          </span>
          </form>
        </div>
      </div>

      <div>
        {search.query.trim() ? (
          /* ---------------------------------- free-text results win over everything */
          search.query.trim().length < SEARCH_MIN ? (
            <p className="t-sm px-1 py-4 text-[var(--ink-3)]">{t('Type at least {n} letters to search.', { n: SEARCH_MIN })}</p>
          ) : searchQ.isPending ? (
            <Skeleton className="h-[160px] w-full" />
          ) : queryHits.length === 0 ? (
            <EmptyState
              icon="search"
              title={t('Nothing matching “{q}”', { q: search.query.trim() })}
              body={t('Try a broader word, or pick a category below.')}
              action={
                <Button
                  variant="secondary"
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { query: '' } })}
                >
                  {t('Clear search')}
                </Button>
              }
            />
          ) : (
            <section aria-label={t('Search results')}>
              <SectionHead
                title={t('Results')}
                aside={
                  <>
                    {plural(queryHits.length, '{n} match', '{n} matches')}
                    {' · '}
                    <Link to="/legal/ranking" className="underline underline-offset-2">
                      {t('How results are ordered')}
                    </Link>
                  </>
                }
              />
              <ul className="ruled">
                {queryHits.map(({ listing: l, owner: o }) => {
                  return (
                    <li key={l.id}>
                      <TapLink
                        to={`/listing/${l.id}`}
                        className="flex w-full items-center gap-4 py-4 text-left transition-opacity duration-[var(--dur-short)] hover:opacity-70"
                      >
                        <Photo
                          src={l.photos?.[0]}
                          alt={l.title}
                          categoryId={l.category}
                          aspect={1}
                          claim={l.id}
                          width={52}
                          thumb
                          className="w-[52px] shrink-0 rounded-[var(--radius-plate)]"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block [overflow-wrap:anywhere] text-body font-semibold">{l.title}</span>
                          <span className="t-sm block [overflow-wrap:anywhere] text-[var(--ink-3)]">
                            {o.name}, {l.district}
                          </span>
                        </span>
                        <span className="tnum shrink-0 text-body font-semibold">
                          {formatMoney(l.ratePerHour, l.currency)}
                          <span className="text-label font-normal text-[var(--ink-4)]"> / h</span>
                        </span>
                        <Icon
                          name="chevron-right"
                          size={18}
                          className="shrink-0 text-[var(--ink-4)]"
                        />
                      </TapLink>
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
            <nav aria-label={t('Categories')} className="rail mt-2 pb-2 md:m-0 md:mt-4 md:flex-wrap md:gap-2 md:p-0">
              {CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => send({ type: 'SEARCH_CHANGED', patch: { categoryId: c.id } })}
                  // An icon row (owner, 2026-09-27; Airbnb, Uber): a tile with
                  // the category's mark and its name under it, not a form chip.
                  className="group flex w-max min-w-[76px] max-w-[max(120px,7.5rem)] shrink-0 flex-col items-center gap-2 pt-1 text-center"
                >
                  {/* The category's object (VD-14): 56 px, springs when pressed. */}
                  <CategoryObject id={c.id} size={56} className="transition-transform duration-[var(--dur-long)] ease-[var(--spring-bouncy)] group-hover:-translate-y-0.5 group-active:scale-110" />
                  <span className="text-label font-medium text-[var(--ink-2)]">{c.label}</span>
                </button>
              ))}
            </nav>

            <SectionHead
              title={t('Free today near you')}
              aside={spotlight.length > 0 ? String(spotlight.length) : undefined}
              className="mt-4"
            />
            {spotQ.isPending ? (
              // Until the first answer: the rail's shape, never a false "nothing free" (V9-2).
              <div className="space-y-3" role="status" aria-label={t('Loading')}>
                <Skeleton className="aspect-[16/9] w-full rounded-[var(--radius-m)]" />
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                  <Skeleton className="aspect-[4/3] w-full rounded-[var(--radius-m)]" />
                  <Skeleton className="aspect-[4/3] w-full rounded-[var(--radius-m)]" />
                  <Skeleton className="hidden aspect-[4/3] w-full rounded-[var(--radius-m)] md:block" />
                </div>
              </div>
            ) : spotlight.length === 0 ? (
              <EmptyState
                icon="clock"
                title={t('Nothing free near you today')}
                body={t('Nothing is free within {distance} today. A wider area usually finds something.', { distance: formatRadius(search.maxDistanceKm) })}
                action={
                  <Button
                    variant="secondary"
                    onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: 90 } })}
                  >
                    {t('Search the whole region')}
                  </Button>
                }
              />
            ) : (
              <>
                {/* A rail of photographs, each with its hour tag (VD-10): the
                    first thing seen is what is free, at a size where one weak
                    photo cannot own the screen. A page shows four across. */}
                <ul className="rail pb-2 md:m-0 md:grid md:grid-cols-4 md:gap-6 md:p-0">
                  {spotlight.slice(0, allSpots ? undefined : 9).map((s, n) => (
                    <li key={s.listing.id} className="md:w-auto">
                      <SpotCard spot={s} to={`/listing/${s.listing.id}`} priority={n < 2} />
                    </li>
                  ))}
                </ul>
                {!allSpots && spotlight.length > 9 && (
                  <div className="mt-6">
                    <Button variant="secondary" onClick={() => setAllSpots(true)}>
                      {t('Show all {n}', { n: spotlight.length })}
                    </Button>
                  </div>
                )}
              </>
            )}


            <SectionHead title={t('All categories')} className="mt-14 md:mt-20" />
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
                    className="group flex w-full items-center gap-3 py-3.5 text-left transition-opacity duration-[var(--dur-short)] hover:opacity-60"
                  >
                    <Icon
                      name={categoryIcon(c.icon)}
                      size={18}
                      strokeWidth={1.6}
                      className="shrink-0 text-[var(--ink-3)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-body font-semibold">{c.label}</span>
                      <span className="t-sm block [overflow-wrap:anywhere] text-[var(--ink-4)]">{c.blurb}</span>
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
            <div className="pt-6">
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
                {formatRadius(search.maxDistanceKm)}
              </Chip>
              {/* The chosen day stays in view and comes off in one tap (UX-55). */}
              {search.day && (
                <Chip selected onClick={() => send({ type: 'SEARCH_CHANGED', patch: { day: null, from: null } })}>
                  {nextDays(14).find((d) => d.value === search.day)?.label ?? search.day}
                  {search.from !== null ? ` · ${t('from {time}', { time: time(new Date(2000, 0, 1, search.from).toISOString()) })}` : ''}
                  <Icon name="close" size={14} strokeWidth={2.4} />
                </Chip>
              )}
            </div>

            {matches && matches.length > 0 && (
              // Wraps at 200 % text instead of pushing Sort off the screen.
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] py-3">
                <p className="t-sm text-[var(--ink-3)]">
                  <span className="tnum font-semibold text-[var(--ink)]">{matches.length}</span>{' '}
                  {matches.length === 1 ? t('bookable slot') : t('bookable slots')}
                  {/* P2B Art. 5: how results are ordered, one tap from the results (H-3). */}
                  {' · '}
                  <Link to="/legal/ranking" className="underline underline-offset-2">
                    {t('How results are ordered')}
                  </Link>
                </p>
                <div className="flex max-w-full flex-wrap items-center gap-2">
                  {/* A map answers "which of these is nearest", which is only a
                      question once there are results, so it lives here, not on
                      the way in. */}
                  <button
                    onClick={() => setShowMap((v) => !v)}
                    aria-pressed={showMap}
                    className={`tap inline-flex min-h-[44px] items-center gap-1.5 rounded-[var(--radius-capsule)] border px-3 text-label font-medium transition-colors duration-[var(--dur-short)]
                      ${
                        showMap
                          ? 'border-[var(--field)] bg-[var(--field)] font-semibold text-[var(--on-field)]'
                          : 'border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--ink-4)]'
                      }`}
                  >
                    <Icon name="pin" size={15} strokeWidth={2.1} />
                    {showMap ? t('List') : t('Map')}
                  </button>
                  <label className="relative t-sm text-[var(--ink-3)]">
                    <span className="sr-only">{t('Sort results')}</span>
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value as SortKey)}
                      className="min-h-[44px] appearance-none rounded-[var(--radius-control)] border border-[var(--line)] bg-transparent pl-3 pr-8 text-label font-medium text-[var(--ink-2)]"
                    >
                      <option value="best">{t('Best match')}</option>
                      <option value="price">{t('Cheapest')}</option>
                      <option value="soonest">{t('Soonest')}</option>
                      <option value="nearest">{t('Nearest')}</option>
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
                visual={<CategoryObject id={meta.id} size={96} />}
                title={t('Nothing matches that yet')}
                body={
                  meta.mode === 'window'
                    ? t('Nobody within {distance} has {duration} free {days}. A shorter booking or a wider radius usually fixes it.', { distance: formatRadius(search.maxDistanceKm), duration: durationLabel(search.hours), days: plural(search.withinDays, 'in the next 24 hours', 'in the next {n} days') })
                    : t('No machine within {distance} can finish {n} {unit} by then. Try a longer lead time or a wider radius.', { distance: formatRadius(search.maxDistanceKm), n: search.quantity, unit: meta.unitNoun ?? '' })
                }
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: 90 } })}
                    >
                      {t('Widen to {distance}', { distance: formatRadius(90) })}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => send({ type: 'SEARCH_CHANGED', patch: { withinDays: 21 } })}
                    >
                      {t('Allow 3 weeks')}
                    </Button>
                  </div>
                }
              />
            ) : showMap ? (
              <div className="pb-2">
                <CapacityMap
                  level={mapLevel}
                  onLevel={setMapLevel}
                  districts={districts}
                  home={home}
                  radiusKm={search.maxDistanceKm}
                  cityStats={cityStats}
                  onOpen={(id) => nav(`/listing/${id}`)}
                  onPickCity={pickCity}
                  // The same results as the list, with the same filters: never the
                  // unfiltered "free today" set.
                  pins={matches.map(({ match: m, listing: l }) => {
                    const soon = Date.parse(m.start) - Date.now() < 3 * 3_600_000
                    return {
                      id: l.id,
                      district: l.district,
                      freeNow: soon,
                      label: `${l.title}, ${l.district}, ${t('free {when}', { when: relative(m.start) })}`,
                    }
                  })}
                />
              </div>
            ) : (
              <ul className="ruled border-t border-[var(--line)]">
                {matches.map(({ match: m, listing, owner }, i) => (
                  <li key={m.listingId}>
                    <ListingCard
                      listing={listing}
                      owner={owner}
                      match={m}
                      rank={sort === 'best' ? i : undefined}
                      to={`/listing/${m.listingId}?slot=${m.slotId}`}
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
        title={t('Filters')}
        footer={
          <Button block size="lg" onClick={() => setFiltersOpen(false)}>
            {plural(matches?.length ?? 0, 'Show {n} result', 'Show {n} results')}
          </Button>
        }
      >
        <div className="space-y-7 pb-4">
          {/* When (UX-15): a day and a start hour, so "Saturday at 10:00" is a
              search, not a scroll through every window. */}
          <FilterGroup label={t('When?')} strip>
            <Chip selected={!search.day} onClick={() => send({ type: 'SEARCH_CHANGED', patch: { day: null, from: null } })}>
              {t('Any time')}
            </Chip>
            {nextDays(Math.min(14, search.withinDays)).map((d) => (
              <Chip key={d.value} selected={search.day === d.value} onClick={() => send({ type: 'SEARCH_CHANGED', patch: { day: d.value } })}>
                {d.label}
              </Chip>
            ))}
          </FilterGroup>
          {search.day && (
            <FilterGroup label={t('From')}>
              <Chip selected={search.from === null} onClick={() => send({ type: 'SEARCH_CHANGED', patch: { from: null } })}>
                {t('Any hour')}
              </Chip>
              {[8, 10, 12, 14, 16, 18, 20].map((h) => (
                <Chip key={h} selected={search.from === h} onClick={() => send({ type: 'SEARCH_CHANGED', patch: { from: h } })}>
                  {time(new Date(2000, 0, 1, h).toISOString())}
                </Chip>
              ))}
            </FilterGroup>
          )}
          {meta?.mode === 'window' ? (
            <FilterGroup label={t('How long do you need it?')}>
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
            <FilterGroup label={t('How many {unit}?', { unit: meta?.unitNoun ?? t('parts') })}>
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

          <FilterGroup label={t('How far will you travel?')}>
            {RADII.map((r) => (
              <Chip
                key={r}
                selected={search.maxDistanceKm === r}
                onClick={() => send({ type: 'SEARCH_CHANGED', patch: { maxDistanceKm: r } })}
              >
                {formatRadius(r)}
              </Chip>
            ))}
          </FilterGroup>

          {/* A picked day already says when; the horizon only matters without one (UX-55). */}
          {!search.day && <FilterGroup label={t('Needed within')}>
            {HORIZONS.map((d) => (
              <Chip
                key={d}
                selected={search.withinDays === d}
                onClick={() => send({ type: 'SEARCH_CHANGED', patch: { withinDays: d } })}
              >
                {d === 1 ? t('24 hours') : plural(d, '{n} day', '{n} days')}
              </Chip>
            ))}
          </FilterGroup>}

          {matches && matches.length > 0 && (
            <p className="t-sm text-[var(--ink-4)]">{t('Soonest right now is {when}.', { when: when(matches[0].match.start) })}</p>
          )}
        </div>
      </Sheet>
      </PhotoGrid>
    </Screen>
  )
}

/* ------------------------------------------------------------------ pieces */

/** The next `n` calendar days on this device: value "2026-10-03", label "Sat 3 Oct". */
function nextDays(n: number): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = []
  const d = new Date()
  for (let i = 0; i < n; i++) {
    const at = new Date(d.getFullYear(), d.getMonth(), d.getDate() + i, 12)
    const value = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}`
    out.push({ value, label: i === 0 ? t('Today') : dayShort(at.toISOString()) })
  }
  return out
}

/**
 * The search lives in the URL (`?q=…&cat=…&h=…&km=…&days=…&n=…`), so a search
 * can be shared or bookmarked and the back button undoes a category. A URL we
 * did not write ourselves (arriving, back, forward) is read into the search;
 * after that the search writes the URL.
 */
function useSearchInUrl() {
  const { state, send } = useCappy()
  const [params, setParams] = useSearchParams()
  const written = useRef<string | null>(null)
  const { search } = state

  const urlFor = (s: typeof search) => {
    const next = new URLSearchParams()
    const keptSort = params.get('sort')
    if (keptSort) next.set('sort', keptSort)
    if (s.query.trim()) next.set('q', s.query.trim())
    if (s.categoryId) {
      next.set('cat', s.categoryId)
      if (category(s.categoryId).mode === 'window') next.set('h', String(s.hours))
      else next.set('n', String(s.quantity))
      next.set('km', String(s.maxDistanceKm))
      next.set('days', String(s.withinDays))
      if (s.day) next.set('on', s.day)
      if (s.day && s.from !== null) next.set('at', String(s.from))
    }
    return next
  }

  // URL → search, when the URL changed without us.
  useEffect(() => {
    if (params.toString() === written.current) return
    written.current = params.toString()
    const num = (k: string) => (params.get(k) ? Number(params.get(k)) : undefined)
    const cat = params.get('cat')
    send({
      type: 'SEARCH_CHANGED',
      patch: {
        query: params.get('q') ?? '',
        categoryId: cat && CATEGORIES.some((c) => c.id === cat) ? (cat as (typeof CATEGORIES)[number]['id']) : null,
        ...(num('h') ? { hours: num('h')! } : {}),
        ...(num('n') ? { quantity: num('n')! } : {}),
        ...(num('km') ? { maxDistanceKm: num('km')! } : {}),
        day: /^\d{4}-\d{2}-\d{2}$/.test(params.get('on') ?? '') ? params.get('on') : null,
        from: params.get('on') && num('at') !== undefined && num('at')! >= 0 && num('at')! < 24 ? num('at')! : null,
        // Snapped to an option the filter sheet offers, so they always agree.
        ...(num('days')
          ? { withinDays: HORIZONS.reduce((a, d) => (Math.abs(d - num('days')!) < Math.abs(a - num('days')!) ? d : a)) }
          : {}),
      },
    })
  }, [params, send])

  // Search → URL.
  useEffect(() => {
    if (written.current === null) return
    const next = urlFor(search).toString()
    if (next === written.current) return
    // Opening or leaving a category is a step back undoes; typing just updates.
    const stepped = new URLSearchParams(written.current).get('cat') !== (search.categoryId ?? null)
    written.current = next
    setParams(new URLSearchParams(next), { replace: !stepped })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, setParams])
}

/** A labelled row of chips in the filter sheet. */
function FilterGroup({ label, children, strip = false }: { label: string; children: ReactNode; strip?: boolean }) {
  return (
    <div>
      <p className="t-h4 mb-3">{label}</p>
      {/* A long run of options scrolls sideways as one row rather than wrapping
          into a wall of chips (UX-55). */}
      <div className={strip ? 'no-scrollbar -mx-5 flex gap-2 overflow-x-auto px-5' : 'flex flex-wrap gap-2'}>{children}</div>
    </div>
  )
}

/**
 * The lead item. A tall plate at full width with the opening time set across
 * it, and the details below in a single line of small type.
 */
/** One thing that is free soon: what it is, when, and what it costs. */
function SpotCard({ spot, to, priority = false }: { spot: Spotlight; to: string; priority?: boolean }) {
  const qc = useQueryClient()
  return (
    <div data-card className="group relative w-[240px] text-left md:w-full">
      <Photo
        src={spot.listing.photos?.[0]}
        alt={spot.listing.title}
        categoryId={spot.listing.category}
        aspect={4 / 5}
        claim={spot.listing.id}
        width={480}
        priority={priority}
        sizes="(min-width: 768px) 25vw, 240px"
        className="press-card rounded-[var(--radius-card)] shadow-[var(--shadow-1)]"
      >
        <WhenChip start={spot.offer.start} />
        <SaveButton id={spot.listing.id} title={spot.listing.title} />
      </Photo>
      <span className="block pt-3">
        <TapLink
          to={to}
          prefetch={() => qc.prefetchQuery({ queryKey: ['listing', spot.listing.id], queryFn: () => getListing(spot.listing.id) })}
          className="[overflow-wrap:anywhere] block min-h-[48px] text-left text-body-l font-semibold after:absolute after:inset-0 after:content-['']"
        >
          {spot.listing.title}
        </TapLink>
        <span className="mt-1.5 flex items-baseline justify-between gap-2">
          <span className="t-sm tnum min-w-0 [overflow-wrap:anywhere] text-[var(--ink-4)]">
            {/* Trust at a glance, before anyone opens the listing. */}
            {rating(spot.owner) !== null && (
              <span className="mr-2 font-semibold text-[var(--ink-2)]" title={t("The owner's rating across all their jobs")}>
                {/* No "Host" label here: on a phone-width card it pushed the distance off (V3-17). */}
                ★ {oneDecimal(rating(spot.owner)!)}
              </span>
            )}
            {rating(spot.owner) === null && (
              <span className="mr-2 font-semibold text-[var(--ink-2)]">{t('New host')}</span>
            )}
            {formatDistance(spot.distanceKm)}
          </span>
          {/* "5 €" beside "212 €" with no unit could not be compared. This is the
              cheapest real booking, so it is labelled as a floor. */}
          <span className="tnum shrink-0 text-body font-semibold">
            <span className="mr-1 text-label font-normal text-[var(--ink-4)]">{t('from')}</span>
            {formatMoney(spot.fromPrice, spot.currency)}
          </span>
        </span>
      </span>
    </div>
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
