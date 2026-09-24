# Cappy

> Rent the hour, not the thing.

Capacity is idle most of the time: a printer free overnight, a PA rig between
gigs, a CNC mill with a gap between contracts. Cappy sells those hours.

**One network, nine categories, three groups.** There is no consumer/industry
split. A buyer who books a laser cutter on Monday, a powder coater on Wednesday
and a pallet to Milan on Friday is one buyer, not three markets. The same graph
is what lets a neighbour sell hours on a printer in a spare room, because from
the engine's point of view that is the same kind of object as a factory selling
second-shift capacity.

| Group | Categories | Mode |
| --- | --- | --- |
| **Make** — turn a drawing into parts | Fabrication · 3D printing · Finishing · Print & signage | batch |
| **Move** — get it across Europe | Freight · Warehousing | batch / window |
| **Equip** — borrow the machine | Workshop & tools · Event & AV · Creator kit | window |

77 listings across 8 cities, from a €4/hour bike stand to a €195/hour metal
printer, because the argument only holds if both ends of that range live in one
graph.

Freight is in there on purpose. It is the step that makes capacity in Lumezzane
usable from Kreuzberg, and without it a pan-European capacity graph is a
directory of places you cannot reach. Finishing is there for the same reason: a
part that cannot be anodised is not a delivered order.

Fabrication is one category rather than six processes. The process lives on the
listing's `machine`, which is where a buyer actually reads it, and splitting the
browse grid by process only ever split the liquidity.

A mobile-first installable PWA. No backend, no accounts, no card details.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run check    # domain self-check, 12 assertions, no test framework
npm run build
```

## On your phone

Deploy the static build (Vercel, Netlify, Cloudflare Pages), then in Safari:
**Share → Add to Home Screen**. Full-screen, own icon, works offline.

`npm run dev` also serves on your LAN for a quick look, but a service worker needs
HTTPS, so install from a deployed URL for the real thing.

## Architecture

Written to grow into the real product. Boundaries, not extra code.

```
src/domain/   pure. no React, no fetch, no storage, moves to a server or RN untouched
src/data/     repo.ts is the ONLY module that knows where data lives, and it is async
src/app/      theme tokens, components, screens, and a reducer over domain events
```

**Rules worth keeping:**

- `domain/` imports nothing from `app/` or `data/`.
  Check it: `grep -rE "react|fetch|localStorage" src/domain/` must be empty.
- `data/repo.ts` is async over local arrays today. That is the whole reason swapping
  in a backend later touches one file and zero call sites.
- Reducer actions are domain events (`BOOKING_REQUESTED`, `LISTING_ADDED`,
  `BOOKING_RATED`), so a server grows around this shape instead of replacing it.
- Money is integer cents everywhere. `formatEur` never rounds €3.50 up to €4.
- `assessFeasibility()` is a named seam: rules today, a probabilistic judgment layer
  later, callers unchanged.

### One engine, two shapes

A booking is either a **window** ("I need it from 18:00 for two hours") or a **batch**
("I need 500 of these by the 14th"). One discriminator on `Listing` and `Requirement`;
feasibility, availability, pricing, matching and ranking are shared.

Ranking is rules: price, soonest, distance, and a trust score built from real
outcomes. Every match carries the `reasons[]` shown to the buyer, because an
explanation is worth more here than a confident score.

## Design system

`src/app/theme.css` holds every token.

Off white paper, Aegean green-black ink (`#20311e`), crimson accent. Crimson
(`#8b0d1a`) does the work of a brand colour, so it carries primary actions, prices, and any window
somebody has booked. Powder blue (`#3e7ca6`) means one thing only, which is
capacity that is still free. Green appears in confirmed and on-time status and
nowhere else. Every colour that carries words was measured against the surface
it sits on and clears WCAG AA, and fills and graphics clear 3:1 against their
neighbours. Crimson and powder blue are the one pair that does not, so they are
never set adjacent.

Type is two faces with a fixed rule so they never get mixed at random. Bodoni
Moda (variable, `opsz`) sets the display, h1 and h2, and at display sizes its
optical-size axis opens the stroke contrast right up, which is where the
presence comes from. Archivo handles everything functional: labels, times,
prices, buttons. The ramp runs `t-display` (up to 76px) down to `t-label`
(11px), with tabular numerals on anything that lines up or ticks.

Spacing is a 4px base with a 20px page gutter. Radii are control 8, field 8,
plate 14, card 14, sheet 22. Motion is 160ms for micro-interactions and 200 to 340ms for transitions,
always decelerating, and `prefers-reduced-motion` is respected. The only motion
nobody triggers is the "free now" dot.

Accessibility: AA verified in both directions, visible focus rings, 44px
minimum tap targets (small controls use the `.tap` expanded hit area), labels
above inputs, validation on blur, and errors next to their own field.

Light only, by choice. `color-scheme: light` keeps native controls and
scrollbars light even on a phone set to dark.

### Photographs, and what the plate is for now

Listings carry the owner's own photographs. The first is the cover.

The rule here used to be that a listing has no photograph, on the grounds that a
stock photo of somebody else's machine would be a lie. That was right about stock
photography and wrong about this product. These are pictures an owner takes of
their own kit, which is the most honest thing on a listing, and a buyer choosing
between two mills wants to see the two mills.

What replaced photographs was a dark plate printing the next free hour. It worked
as a thumbnail and failed as a grid: four panels reading 9h, 7h, 6h, 9h tell you
exactly when four things are free and never once what any of them is. The
photograph answers *what*, which is the question a buyer asks first.

So the plate narrows to the three jobs it is actually good at:

- the fallback when a listing has no upload yet
- the idle-hours band, where the figure genuinely is the content
- the availability section on a detail page

Time did not disappear; it moved to a chip on the photograph. That chip is the
only place the palette does real work, and it carries the whole thesis in about
sixty pixels: **ice** means you can have it now, **white** means you can have it
later, **crimson** means this is the window you are booking. A photograph is an
uncontrolled upload, so the chip sits on a bottom-third scrim and a darker glass
tint than glass over a known surface would need.

Photos in `src/data/seed.ts` are curated stand-ins handed out by rotation within a
category, not by hashing the id. A hash spreads evenly in theory and in practice
puts the same picture on two cards side by side, which reads as a bug rather than
as a placeholder.

### Feedback, and the things that bring people back

A marketplace for physical capacity runs on trust, and the C2C plan says so in
as many words: trust is part of the product. The ranking already learned from
outcomes; nothing let a stranger *read* them. Now:

- **Reviews on every listing.** A summary leads with the three things a buyer is
  trying to find out (the average, the share ready on time, and the tags people
  pick most, counted), then the words, three at a time.
- **Rating writes a review.** After a booking you rate it, pick what stood out
  from a fixed vocabulary (`REVIEW_TAGS`) and optionally say something. It shows
  on the listing immediately. It is not stored twice: a rated booking already
  carries the outcome, and `reviewsFor` reads it back as a review.
- **Saved.** A heart on every card. Buyers compare three printers before booking
  one, and without a shortlist the only way back was to search again.
- **Book again.** A finished booking that went well is the likeliest next
  booking there is; the old footer sent people back to a search they had done.

Seed reviews are written from each owner's real record, so a shop with thirty
jobs at 4.9 reads like 4.9, and an owner with none shows as new. The self-check
holds them to it, and to never repeating a sentence on one listing.

### Liquid glass

Chrome is glass, built to Apple's iOS 27 kit rather than to a blur-and-hope
approximation. `.glass`, `.glass-thin` and `.glass-strong` are the kit's three
frost levels; `.glass-dark` is the same material over an Aegean plate. Each pane
is a tint under a `backdrop-filter`, a 1px rim drawn as a *gradient* lit from
135° (a flat border is what makes web imitations read as a grey box with a blur
behind it), and a short specular sweep across the top. `.scroll-edge` is the
kit's soft scroll edge: content fades out behind a floating pane instead of
being cut off by a rule.

Two things will silently kill all of it, and both bit this codebase:

- **`isolation: isolate` on the pane.** It makes the element its own backdrop
  root, so there is nothing behind it to filter and `backdrop-filter` becomes a
  no-op. `backdrop-filter` already establishes the stacking context the
  `z-index: -1` pseudo-elements need, so isolation buys nothing anyway.
- **A filled opacity animation on any ancestor.** `.anim-screen` wraps every
  screen and used `animation-fill-mode: both`. An element left holding a filled
  opacity animation stays a backdrop root for good, which disabled the glass in
  the entire app. Every keyframe here ends on its property's natural value, so
  they fill `backwards` and never `forwards`.

Glass rules live in `@layer components` so a call site's `fixed` or `sticky`
utility still wins over the `position: relative` a pane needs by default.

### The cover

A listing has no photograph, and a stock photo of someone else's machine would
be a lie. `Cover` prints a plate instead: the category's own
paper, one large glyph, and a seven-day strip showing which days have hours in
them. Ice where there is time to sell, crimson where a window is
taken. The plate carries the same lit rim as every glass surface, so a plate and
the dock read as one material family.

**The plate grows its information, not its type.** Below 330px of plate the week
is a seven-tick index along the bottom edge: enough to say "free around Thursday"
at a glance. Above it, that index becomes the timetable it was always an
abbreviation of, with the days named and each bar's height set by the hours
actually free. Same seven numbers, drawn at a size where they can be read.

That is the fix for a plate that used to be a void. Bodoni past about 130px stops
being a number — the hairlines thin to nothing and the stems read as bare bars,
so "11h" became three rectangles in an acre of green. The figure is capped
instead, and the room a wide plate opens up goes to the week, which is the part a
buyer wants at that size. The figure is also divided by glyph count, because "6h"
and "18:00" are the same component and a size that fits two glyphs runs a
five-glyph time off the edge.

`CapacityBar` on the detail screen still draws the real week to scale with a
legend; the plate's timetable is the summary, not a replacement for it.

### Responsive

Phone-first at 560px max. The dock is a floating glass capsule; from 768px it
becomes a left rail and content widens to 760px. Safe-area insets are handled on the dock, sticky
footers and sheets.

## What is not real

Hosts, machines, prices and availability in `src/data/seed.ts` are realistic examples,
not real people or businesses. Requests you send are auto-accepted after ~5 s so the
whole flow is walkable; requests *to* you (the Earn inbox) are answered for real.
No money moves.

## Before sharing the link

- Fill in the Impressum placeholders in `src/app/screens/Profile.tsx` (§5 DDG).
- `.env` holds a live `JEV_API_KEY` and is gitignored. Keep it that way, a key
  committed once stays in history even after the file is deleted.
