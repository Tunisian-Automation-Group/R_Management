# Cappy UI/UX review against best-in-class apps (2026-09)

The UI/UX lead's review of the web app (desktop) and the app version (390 × 844)
in EN, DE and FR, as the demo buyer, the second host and staff. It covers
`web/src/app` at `25e79d3`, looked at in the browser on
`http://127.0.0.1:5173` on 2026-09-26. It follows on from
[`2026-09-app-ux.md`](2026-09-app-ux.md): that document was about **flows and edge
cases** (U-1 … U-40, mostly done). This one is about **craft**: how the app
looks, moves and feels next to Airbnb, Vinted, Turo, Revolut and Linear.

The UX-n checklist at the end is copied into [`../TASKS.md`](../TASKS.md).
Builders implement it. This document proposes; it changes no code.

**How the screens were seen.**
- Desktop: a 1440 px Chrome window.
- Phone: a 390 × 844 iframe of the same origin.
- The "Continue as demo …" buttons for buyer, host 2 and staff. Sign-in worked on 127.0.0.1; there was no CORS problem.
- No booking, listing or message was created. The confirm sheet and the listing form were opened and filled, but never submitted.
- Screenshot references below name the screen, the viewport and the state.

**GIFs recorded** (`gif_creator`; saved to `~/Downloads`, not into the repo):
- `cappy-book-a-listing-phone-en.gif`: Explore → search "plunge" → listing → pick a start → Request → the confirm sheet.
- `cappy-add-a-listing-phone-en.gif`: Earn → New listing → category → the one-page form, top to bottom, to the earnings preview.
- `cappy-message-the-renter-phone-en.gif`: host 2 → Bookings → I'm hosting → Next up → the chat in the booking, a message typed but not sent.

---

## 1. Executive summary

Cappy is **functionally ahead of its craft**. The flows, the legal texts, the
edge cases, the localisation and the trust copy are better than most launched
marketplaces: U-1 … U-40 are nearly all done. The visual layer, though, has a
strong idea that is not yet carried out well enough to pass for a top-tier app.

The idea is an editorial, "departure board" identity: Bodoni display type,
dark green plates, crimson actions and Liquid-Glass chrome. Three problems
break it:

1. **The imagery is wrong.** A 3D printer is shown with a photo of smokestacks, and a plunge saw with an electrician at a fuse box. The same photo repeats down the grid.
2. **The Didone face is used for figures.** In "€3.40" the € reads as "C", and in "1.4 m" the 1 reads as "I".
3. **The app does not feel native.** The motion is fade-only, sheets cannot be dragged, there are no haptics, and there is no dark mode.

Two structural gaps matter just as much:
- **There is no inbox.** Messages live inside a booking.
- **Search has no "when".** You cannot ask for Saturday 10:00.

### Scores (1 = far from best-in-class, 5 = on par with Airbnb, Revolut or Linear)

| Area | Score | Why |
|---|---|---|
| Visual hierarchy and identity | **3** | A distinctive, confident identity (Bodoni + Archivo, green plates, one hot colour) and clear page structure. Let down by the imagery and by display type used for data. |
| Typography | **2** | The ramp in `theme.css` is good. But 21 ad-hoc rem sizes sit outside it (`text-[0.9062rem]` × 17 and others). Prices and model numbers are set in Bodoni (€ looks like C, 1 like I). The dock labels are 10.5 px. |
| Spacing and layout | **3** | A consistent 20 px gutter and a good desktop product-page grid. The phone listing loses about 165 px to the dock plus the sticky bar. The staff console and forms sit in a 760 px column on a 1440 px screen. |
| Colour and contrast | **3** | AA was measured for text (a good discipline). But crimson carries actions, errors, badges and "Nadia receives €13.60" alike. The crimson CTA on the green welcome plate is about 1.4:1 against its background. Disabled buttons fade to 30% pink. |
| Imagery | **1** | Stock photos that do not match the listing. One photo per listing, no gallery. Grey boxes until the image arrives (seconds on the desktop grid), no blur placeholder. Your own listings show a clock plate, not a photo. |
| Iconography | **3** | A coherent 1.7–2 px stroke set in `Icon.tsx`. The category icons are too small (14 px) to tell apart; no filled/active variants. |
| Motion and feedback | **2** | View transitions and a hero morph exist, and reduced motion is respected. But every screen only fades. Sheets slide up and cannot be dragged. No press states, no optimistic updates, no haptics. |
| Navigation (phone vs desktop) | **3** | The glass dock with a centre "+" is good, and the desktop gets a real top bar and footer. But there is no Messages destination. The dock stays on detail screens. Staff get consumer chrome with a "List capacity" CTA. The filter sheet is a phone sheet on the desktop. |
| Forms and input | **3** | Labels above fields, errors inline, correct `autocomplete` and `inputmode`, money input in minor units. But AddListing is one 3,200 px page with "Publish listing" pinned before anything is filled in. |
| Search and discovery | **2** | Text search, categories, filters with a "Show 7 results" count, sort. But there is no date/time picker, and "needed within 14 days" is not a date. The "map" is an abstract radial diagram whose pins cover the district label. Results rows truncate titles and differ from the home cards. The km→mi conversion gives "6.2 mi / 19 mi / 47 mi". |
| Booking and checkout funnel | **3** | The total with fee is shown up front (Airbnb standard), plus the policy in plain words, "Your card is only held", and a clear confirm sheet. But the renter is shown "Nadia receives €13.60" in crimson. The fee is called "service fee" and "Cappy fee" in different places. The desktop buy box cannot change the time. There are no wallets (Apple Pay / Google Pay) and the Stripe Element is unthemed. |
| Trust and safety signals | **3** | A verified shield, private/trader status, response time, "95% on time", a safety card, and warnings in chat. Undermined by the stock photos and by reviews shown untranslated in FR/DE. The verification badge does not say what was checked. |
| Empty, error and offline states | **4** | Empty states with a reason and an action, an offline bar, mapped decline codes, a request id on errors (U-11, U-23, U-24). |
| Perceived performance | **2** | Lazy chunks, `loading="lazy"`, CLS 0 on the listing. But the LCP image has no `srcset`, `width`/`height` or `fetchpriority` (LCP 2.26 s locally, one image). Grid photos pop in seconds late onto grey. |
| Accessibility | **3** | Focus trap and return in sheets, `role="status"` toasts, 44 px targets by default, reduced motion, Dynamic Type sizing. But the dock labels are 10.5 px, the disabled-state contrast is poor, there is no automated axe run (U-30 open), and the chat's `scrollIntoView` moves the page on open. |
| Consistency | **2** | Radii run from 2 to 28 px (and pill) with no rule. Buttons are rectangles, but the header CTA, the language switch and the back button are pills. Two nested tab bars on Bookings. The results list and the home grid look like two apps. |
| Dark mode and theming | **1** | Light only, by choice (`color-scheme: light`). Tokens exist as CSS variables but are not tiered or exported; no Figma variables. |
| Native feel in the shells | **2** | Safe areas, the Android back listener, the push priming sheet and Dynamic Type are done. But there are no `@capacitor/haptics`, `status-bar`, `splash-screen` or `keyboard` plugins. Sheets cannot be swiped away. The sticky action bar will sit on the keyboard in chat. Predictive back is not verified on target SDK 36. |
| Delight | **2** | A live dot, a self-drawing tick, the idle-week chart. Nothing rewards the booking moment. The Earn hero ("€8,591.25 of time nobody is paying you for") guilts people rather than invites them. |
| Staff console | **2** | Honest and complete, but a consumer-styled single column. No queue table, no keyboard flow, ids truncated ("Person l9…"), and no staff chrome. |

**Overall: about 2.5 out of 5.** It is a solid, legally careful product
wearing a first draft of its visual system. The P0 list below takes it to
about 3.5 (credible at launch). P1 takes it to about 4.

---

## 2. Findings by area

Each finding gives the screenshot (screen · viewport · state), the problem,
why it matters with a source, and the proposal. The UX ids point to the
checklist in §5.

### 2.1 Imagery (the biggest single problem)

**F-1 Photos do not show the thing listed.**
- *Screenshots:*
  - Explore · desktop and phone · signed in as buyer: "Bambu H2D, two colour" (a 3D printer) is a photo of industrial smokestacks. The next two cards (Formlabs, Prusa) reuse the same photo.
  - Listing `l9` · both viewports: the Festool plunge saw is shown as an electrician at a fuse box.
  - The search results for "saw" show a solid green square for the bandsaw.
- *Why it matters:*
  - NN/g names design quality and accurate, current content among the four factors that decide whether a site is trusted (https://www.nngroup.com/articles/trustworthy-design/).
  - On a P2P marketplace the photo *is* the proof that the thing exists. Airbnb's 2025 rebuild puts verified identity and real media first (https://news.airbnb.com/airbnb-2025-summer-release/).
- *Proposal:*
  - Seed data uses category-true photos: one set per category, never reused within a viewport.
  - The product shows **the owner's photos only**. With no photo, show a designed category illustration with the listing's name, never an unrelated stock photo. **UX-1**
  - Listing pages get a real gallery: swipe on the phone, a 1+4 mosaic on the desktop, full-screen with pinch, "2 / 5", and alt text "Photo 2 of 5, {title}". **UX-2**
  - AddListing asks for at least 3 photos, with shot hints (whole thing, detail, where it lives). **UX-19**

**F-2 Images arrive late onto grey.**
- *Screenshots:*
  - Explore · desktop · first load: the whole grid is flat grey boxes with a dark gradient for about 2–4 s.
  - Listing · phone · first paint: the hero fades from a grey box.
  - Host Bookings · phone: the alt text "Workshop & tools" is printed inside a broken thumbnail.
- *Why it matters:*
  - LCP should be ≤ 2.5 s at p75 (https://web.dev/articles/lcp). The LCP image should carry `fetchpriority="high"` and never be lazy (https://web.dev/articles/fetch-priority).
  - Sized images and `aspect-ratio` prevent CLS (https://web.dev/articles/optimize-cls).
  - Measured: LCP 2,256 ms on localhost for a single 900 px image with no `srcset`.
- *Proposal:*
  - U-40 (responsive widths) plus a stored **dominant colour or 16 px blurhash** per photo, painted as the placeholder.
  - `fetchpriority="high"` on the hero and the first two cards.
  - `sizes` on every grid image.
  - Hide the alt text on failure (an `onerror` swap to the illustration). **UX-3**

### 2.2 Typography

**F-3 The display serif is used for figures and model numbers.**
- *Screenshots:*
  - AddListing · phone · the earnings preview: "€3.40" set in Bodoni reads as **"C3.10"**.
  - Listing title "Festool TS 55 plunge saw + 1.4 m rail" reads as "I.4 m".
  - "Bambu H2D" reads as "Bambu I I2D".
  - The Earn hero "134" and the review score "4.8" are Didone figures.
- *Why it matters:*
  - For a marketplace, prices and specs are the data people compare.
  - Apple's guidance is to prefer legibility over style for text people must read. Minimum 11 pt, and contrast rises for thin strokes (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/accessibility.json).
  - A Didone's hairlines vanish at text sizes and on low-DPI Android screens.
- *Proposal:* a rule plus a token.
  - **Bodoni only for words at ≥ 28 px** (screen titles, the welcome headline, section heroes).
  - **All figures, prices, times, ratings and user-generated titles go in Archivo** (`t-figure-*` tokens, tabular).
  - Listing titles are user text (model numbers, "+", "×"), so they become Archivo 600 at `title-l`. **UX-4**

**F-4 The ramp is bypassed.**
- *Code:* 21 distinct `text-[…rem]` values outside `.t-*`: 0.9062, 0.8438, 0.7812, 0.5938 and so on. The dock labels are `min(0.6562rem, 14px)`, which is 10.5 px.
- *Why it matters:*
  - A system is only a system if screens use it. Airbnb's DLS treats components as a living set with required and optional parts, one set shared across platforms (https://karrisaarinen.com/dls/).
  - Apple's smallest default text is Caption 2 at 11 pt; tab-bar labels are 10 pt and bold (HIG tab bars, typography).
- *Proposal:*
  - Replace the arbitrary sizes with the 9-step scale in §3.1.
  - Add a lint rule (a `check:tokens` script, like the existing `check:*` scripts) that fails on `text-[` and `rounded-[` literals outside `ui.tsx`.
  - Dock labels at 11 px/600. **UX-5**

### 2.3 Colour and contrast

**F-5 One crimson for everything hot.**
- *Screenshots:*
  - Confirm sheet · phone: "Nadia receives €13.60" in crimson, directly under "You pay €16.00".
  - Profile · buyer: "Earned €0.00" in crimson.
  - The badges, the primary button, the focus ring, "Remove" and the error text are all crimson.
- *Why it matters:*
  - Colour should carry one meaning. Using the same colour for "act here" and for money reads as a warning or a fee.
  - Baymard: 40% of abandonments come from extra costs, and a surprise number next to the total looks like one (https://baymard.com/lists/cart-abandonment-rate).
- *Proposal:*
  - Split into roles: `action` (crimson), `danger` (a red distinct from crimson, e.g. #C4312B), `money-positive` (green), `badge` (crimson), `focus` (blue-ink #2D6479, not crimson).
  - Drop the host payout line from the **renter's** sheet (keep it in the host's views). **UX-6**

**F-6 Weak states.**
- *Screenshots:* Sign in · both viewports: the disabled primary is a 30%-opacity pink with white text. Welcome · phone: the crimson CTA on the dark green plate.
- *Why it matters:* disabled controls are exempt from 1.4.11, but a pink block reads as "broken", not "fill the form first". A button should be told apart from its background at 3:1 (https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
- *Proposal:*
  - Disabled = `surface-sunken` fill + `ink-4` text.
  - Keep the button enabled and validate on press where possible (Baymard, inline validation: https://baymard.com/blog/inline-form-validation).
  - On the welcome plate, the primary becomes `on-field` (ivory) with ink text. **UX-7**

### 2.4 Motion and feedback

**F-7 Screens fade and sheets slide. That is all.**
- *Code:*
  - `anim-screen` is a 220 ms opacity fade for every route.
  - `anim-sheet` is a 300 ms translate with no exit animation (the sheet unmounts at once).
  - There are no press states (`:active` scale) on cards or buttons.
- *Why it matters:*
  - Apple: motion has a purpose, is brief, follows the gesture and "lets people cancel motion" (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/motion.json).
  - NN/g: 100 ms for feedback, 200–300 ms for modals, and over 500 ms drags (https://www.nngroup.com/articles/animation-duration/).
  - M3 splits *spatial* springs (which move things) from *effects* springs (colour and opacity, no overshoot) (https://raw.githubusercontent.com/material-components/material-components-android/master/docs/theming/Motion.md).
- *Proposal:*
  - The motion tokens in §3.4.
  - A push/pop *slide* for drill-down routes (list → detail) on the phone, a crossfade for tab switches, and the hero morph kept.
  - An exit animation for sheets and toasts.
  - `:active` scale 0.98 at 100 ms on cards, rows and buttons.
  - The selected slot chip animates its fill (`effects-fast`). **UX-8**

**F-8 Sheets are not draggable.**
- *Screenshots:* Filters · desktop: a phone bottom sheet centred on a 1440 px screen. Confirm request · phone: a grabber is drawn, but the code says it is "decorative".
- *Why it matters:* the HIG says to include a grabber on a resizable sheet, support swipe to dismiss, and use medium and large detents (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/sheets.json). The M3 bottom-sheet max width is 640 dp; on large screens use a dialog or a side sheet (https://raw.githubusercontent.com/material-components/material-components-android/master/docs/components/BottomSheet.md).
- *Proposal:*
  - The `Sheet` gets pointer-driven drag: follow the finger, dismiss past 30% or on a velocity above 0.5 px/ms, rubber-band at the top.
  - Medium and large detents for Filters and Report.
  - A grabber that is a real button cycling the detents.
  - At ≥ 768 px, `Sheet` renders as a centred dialog (max 560 px, scale-in) or a right side sheet for Filters.
  - WCAG 2.5.7: the close button stays as the single-pointer alternative. **UX-9**

**F-9 No optimistic UI.** No `useOptimistic` or `onMutate` anywhere.
- *Screenshots:* saving a listing (the heart), sending a message and toggling a notification setting all wait for the round trip.
- *Why it matters:* 0.1 s feels instant; 1 s keeps flow (https://www.nngroup.com/articles/response-times-3-important-limits/). React 19's `useOptimistic` reverts on failure (https://react.dev/reference/react/useOptimistic).
- *Proposal:* make the heart, sending a chat message (a pending bubble → sent → a failed bubble with retry) and the settings toggles optimistic. **Never money.** **UX-10**

**F-10 No haptics.**
- *Why it matters:* the shells promise native, and a tick on success is part of how Revolut and Airbnb confirm an action. `@capacitor/haptics` offers impact light/medium/heavy, notification success/warning/error and selection changes (https://capacitorjs.com/docs/apis/haptics). Pair each with visual feedback and don't overuse them (HIG).
- *Proposal:* a `haptic()` helper that is a no-op on the web:
  - `selectionChanged` on slot, day and chip picks;
  - `impact(Light)` on the heart;
  - `notification(Success)` on a sent request, an accepted booking and a published listing;
  - `notification(Warning)` on a refused payment. **UX-11**

### 2.5 Navigation model

**F-11 There is no inbox.**
- *Screenshots:* Booking detail · phone · buyer: "Messages with Nadia" is the fifth card down a 2,400 px page. Host 2: the only way to a chat is Bookings → I'm hosting → a booking → scroll.
- *Why it matters:* Airbnb's 2025 app has four tabs: Explore, Trips, **Messages**, Profile (https://news.airbnb.com/airbnb-2025-summer-release/). On a two-sided marketplace, the time to first reply is the conversion (the listing shows "Replies in ~1 min").
- *Proposal:*
  - An **Inbox** destination: threads per booking, the other person's avatar, the listing thumb, the last line, unread dots, and a booking-status chip.
  - Dock: **Explore · Bookings · Inbox · Earn · You**. HIG and M3 both allow up to 5 (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/tab-bars.json).
  - The "+" moves into Earn's header and the desktop top bar, because listing is rare for most members.
  - The booking detail keeps a "Message Nadia" row that opens the thread. **UX-12**

**F-12 The dock and the sticky bar stack on detail screens.**
- *Screenshot:* Listing · phone: the price bar (≈ 85 px) plus the dock (≈ 66 px) plus gaps take about 20% of an 844 px screen. Booking detail: "I have collected it / Withdraw" plus the dock.
- *Why it matters:*
  - The HIG keeps tab bars visible in general, but Airbnb, Vinted and Turo hide them on listing detail and checkout to give the buy bar the bottom edge.
  - WCAG 2.4.11: the focused composer must not be hidden by sticky bars (https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/).
- *Proposal:*
  - On the phone, detail routes (`/listing/:id`, `/bookings/:id`, `/earn/new`) hide the dock and show the back chevron. The bar docks to the bottom edge, full width, with the safe area.
  - When an input is focused, the bar hides. **UX-13**

**F-13 Staff work in the shopper's app.**
- *Screenshot:* `/admin` · desktop · staff: a consumer top bar (Explore, Bookings, Earn, "List capacity"), then Cases, Reports and the audit log stacked in a 760 px column. Report rows show "Spam · Person l9…".
- *Why it matters:* staff throughput is a cost at scale. Linear-class tools use dense tables, keyboard shortcuts and a detail pane.
- *Proposal:*
  - A staff shell: its own left rail (Cases, Reports, Held listings, Refund approvals, Audit), full width, no consumer CTA.
  - Queues as tables (age, type, target, SLA timer, assignee).
  - A split view with the detail on the right.
  - `j`/`k`/`Enter`/`e` shortcuts.
  - Ids shown whole, with a copy button. **UX-14**

### 2.6 Search and discovery

**F-14 There is no "when" in search.**
- *Screenshots:* Explore · desktop: a text field and categories only. Filters · desktop: "How long / How far / Needed within 24 h … 21 days". Nothing picks a day or an hour.
- *Why it matters:*
  - Cappy sells hours. Airbnb's search is *Where · When · Who*, and Turo's is *Where · From · Until*.
  - NN/g: mobile faceted search as a tray with a persistent count, and a text "Filter" label (https://www.nngroup.com/articles/mobile-faceted-search/).
- *Proposal:*
  - A composite search pill: **What** (text or category) · **When** (a day strip + a start hour + a duration, defaulting to "Any time in the next 7 days") · **Where** (district and radius).
  - On the phone it opens as a full-screen step sheet. On the desktop it is an expanding bar with popovers.
  - Results show the chosen window's price. **UX-15**

**F-15 The "map" is a diagram.**
- *Screenshot:* Workshop & tools · Map · desktop: dashed radius rings with seven crimson dots clustered over "Kreuzberg", covering the label ("reuzberg"). No streets, no prices on pins, and no list next to it on a 1440 px screen.
- *Why it matters:* the map is where people judge "near me". Airbnb's desktop is a list plus a map, with price pins and "search this area".
- *Proposal:* a real vector map (MapLibre GL with an OSM-based style, or the provider in ADR/FEATURES §4.3), in this order:
  1. price pins that cluster;
  2. a list/map split at ≥ 1024 px;
  3. on the phone, the map full screen with a draggable results sheet (peek, half and full);
  4. "Search this area" after a pan.
  
  Pins keep district-level blur (privacy). **UX-16**

**F-16 Two card languages, truncated titles, odd units.**
- *Screenshots:*
  - The search results for "saw" are 56 px thumbnail rows with no rating.
  - The home grid is big cards.
  - The category results are a third layout.
  - The phone result title "Festool TS 55 plunge sa…" is cut.
  - Filters: "6.2 mi / 19 mi / 47 mi / 93 mi" (km values converted, not re-chosen).
  - "from €19.92" has no unit.
- *Proposal:*
  - One `ListingCard` in two densities, grid and row.
  - Titles wrap to 2 lines.
  - Rating and "Free from 19:30" on every card.
  - Radius steps chosen per unit (1 / 3 / 10 / 25 / 50 mi; 2 / 5 / 15 / 40 / 80 km).
  - The price always with its unit ("from €19.92 / h"), or better the total for the searched window. Baymard on product lists and product pages: https://baymard.com/research/product-page. **UX-17**

**F-17 Applied filters are a single chip.**
- *Screenshot:* category results · desktop: "Workshop & tools ×" and "2 hours · 47 mi" as one chip.
- *Why it matters:* 28% of sites show no overview of the applied filters. Show each value with its own × and a "Clear all" (https://baymard.com/blog/how-to-design-applied-filters).
- *Proposal:* one chip per value (duration, radius, within, sort ≠ best), each removable, and "Clear all". This closes U-21. **UX-18**

### 2.7 Listing, booking and checkout

**F-18 The desktop buy box is read-only.**
- *Screenshot:* Listing · desktop: the right-hand box says "€16.00 · tomorrow, 8:00 AM – 12:00 PM · 4 hours · Request", but the day, the time and the duration are changed 1,000 px down the left column.
- *Why it matters:* Airbnb's reservation card holds the date pickers, because the price is only meaningful with the time. People should not have to hunt for the input that changes the number.
- *Proposal:*
  - The box gets **Day**, **Start** and **Duration** fields (popovers with the same slot grid).
  - The left column keeps the week chart as an overview; tapping a free bar sets the box.
  - On the phone, tapping the sticky bar's time line opens the same picker sheet. **UX-20**

**F-19 A cluttered slot picker.**
- *Screenshot:* Listing · desktop: 15 day chips wrap onto 3 rows, then 10 time chips with a jump from 12:00 PM to 6:00 PM that nothing explains.
- *Proposal:*
  - A horizontal day strip showing weekday, date and a "free hours" dot, scrolled to today.
  - Times grouped Morning / Afternoon / Evening.
  - Unavailable times shown disabled with a reason on tap ("Booked") instead of disappearing, so the gap reads as "taken", not "broken". **UX-21**

**F-20 The confirm sheet mixes the host's money into the renter's decision.**
- *Screenshot:* Confirm request · phone: When · Duration · Where · You pay €16.00 · **Nadia receives €13.60** (crimson) · "Nothing is charged yet" · "Book and pay".
- *Why it matters:* Baymard, the top abandonment cause is costs, and 12% abandon because they cannot see the total (https://baymard.com/lists/cart-abandonment-rate). One clear total, with a breakdown on demand, is the norm.
- *Proposal:*
  - The renter sees: price × hours, the Cappy service fee (one name everywhere, **UX-22**), and the Total.
  - The cancellation policy on one line ("Free cancellation until 10:30 tomorrow"), with the date computed.
  - The payment method row.
  - The button says what happens: "Request and hold €16.00" for a request and "Book and pay €16.00" for instant book, keeping §312j wording in DE ("Zahlungspflichtig anfragen").
  - The host's share is only shown to the host. **UX-23**

**F-21 Payment looks like someone else's form.**
- *Code:* `PayStep` passes no `appearance` to `Elements`, and there is no Express Checkout Element.
- *Why it matters:*
  - 19% abandon because they don't trust the site with their card. Visually enclose the card fields and add a recognisable seal (https://baymard.com/blog/perceived-security-of-payment-form).
  - On a phone, a wallet is one tap.
- *Proposal:*
  - Stripe Appearance API with Cappy tokens (font, radius, colours, focus).
  - An enclosed card panel with a lock and "Payments by Stripe · card held, not charged".
  - The Express Checkout Element (Apple Pay / Google Pay) above the card on the web. In the shells, test the wallets or hide them where the webview cannot run them (Stripe's own caveat, in `2026-09-app-ux.md` §4). **UX-24**

**F-22 Booking detail: one long stack, a premature primary, and the page jumps.**
- *Screenshots:*
  - Booking detail · phone · buyer · confirmed, 21 h before the start: the sticky primary is **"I have collected it"**.
  - The page opens scrolled 477 px down, because `Conversation.tsx:105` calls `scrollIntoView` on the chat's end element when it mounts.
  - Nine cards follow: status, stepper, getting in, owner, messages, safety, photos, help, …
- *Why it matters:* the primary action should be the one that is right *now* (U-37's own rule). A "collected" button a day early invites mis-taps that change money state. A screen that opens mid-page breaks orientation.
- *Proposal:*
  - The primary follows the time. Before the window it is "Message Nadia" plus "Directions"; from 30 min before it is "I have collected it" (with haptic and confirm); after the end it is "Hand back".
  - Destructive actions ("Withdraw") go to an overflow menu, not the sticky bar.
  - Status header: a big state word and a countdown ("Starts in 21 h").
  - Chat moves to the Inbox (UX-12).
  - The chat scroll only scrolls its own container (`block: 'nearest'` inside an `overflow` box, or `scrollTop`), never the page. **UX-25**

### 2.8 Hosting (Earn, AddListing)

**F-23 The Earn hero makes people feel guilty.**
- *Screenshot:* Earn · phone · host 2: "Still idle this week **134** hours · **€8,591.25 of time nobody is paying you for**".
- *Why it matters:*
  - The figure is a hypothetical: every idle hour × the list price. It is shown as a loss, in crimson, as if it were fact.
  - NN/g trust factors: upfront and truthful disclosure.
  - People do not respond well to being told they are losing €8.6k.
- *Proposal:*
  - Lead with a "Today" block: requests waiting with a countdown (exists), hand-overs today, and money actually earned or on the way ("€38.25 earned · €25.50 on the way").
  - Idle time becomes an invitation ("134 h free this week. People nearby search most on Saturdays"), with no euro figure. **UX-26**

**F-24 AddListing is one 3,200 px page.**
- *GIF:* `cappy-add-a-listing-phone-en.gif`. Name, photos, one line, where, address, postcode, price, min/max, extra, discounts, policy, instant book, availability (5 options), access notes, house rules, then the earnings preview at the very bottom. "Publish listing" is pinned the whole time.
- *Why it matters:*
  - Baymard: form *fields*, not steps, drive the burden. Ideal checkouts have about 8 fields (https://baymard.com/blog/checkout-flow-average-form-fields).
  - Airbnb's host flow is a paced step-by-step with progress, and Vinted's upload is photos first.
  - The earnings preview is the motivation, so it belongs next to the price.
- *Proposal:* 5 steps with a progress bar and "Save and exit":
  1. Photos and name
  2. Where
  3. When it's free
  4. Price, with a live "You earn €3.40 / h" beside the field and discounts collapsed under "More pricing"
  5. Rules and review
  
  The primary is "Next" per step. "Publish" appears only on the review. The draft survives, as U-25 already does. **UX-19**

### 2.9 Profile, settings, notifications, help, legal

**F-25 Profile is a long document, not a settings screen.**
- *Screenshot:* You · phone · buyer: an identity card with "Listed 0 · Earned €0.00 (crimson) · Spent €38.00", Saved, Account (Sign out, Sign out everywhere), a notification matrix of checkboxes, Your data (Download / Delete), and the whole "How Cappy works" essay.
- *Why it matters:* the pattern every big app uses is an identity header, then grouped, tappable rows (Personal info, Verification, Payments and payouts, Notifications, Language, Appearance, Privacy, Help, Legal), with Sign out last. Delete account at most two taps deep (Google Play policy, cited in `2026-09-app-ux.md`).
- *Proposal:*
  - Grouped rows with chevrons, each opening its own screen.
  - Notifications become a screen of toggles (switch controls, not checkboxes).
  - Sign out goes to the bottom.
  - Hide "Earned" for someone who has never listed.
  - The "How Cappy works" essay moves to Help. **UX-27**

**F-26 The notifications list is a wall of text.**
- *Screenshot:* Notifications · phone: bold titles plus 3–4 line bodies, with no icon, no unread marker, no grouping by day and no thumbnail.
- *Proposal:*
  - An icon or thumbnail per type, an unread dot and weight, and Today / This week groups.
  - A 2-line clamp.
  - Swipe to mark read (with a button alternative). **UX-28**

**F-27 Help and legal are readable, but plain.**
- *Screenshots:*
  - Help · phone: 11 rows and no search.
  - Terms · phone: good (tabs of legal pages, a "details to be completed" banner).
- *Proposal:*
  - A search field on Help.
  - "Help with a booking" at the top when a booking is active.
  - WCAG 3.2.6 Consistent help: the same Help entry in the same place on every screen (a `?` in the booking and listing headers) (https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/). **UX-29**

### 2.10 Welcome, sign-in, onboarding

**F-28 The welcome shows no product.**
- *Screenshots:* Welcome · desktop and phone: dark green, a Bodoni headline, three icon lines, two buttons. No photo, no example price, no sense of what is on offer. The U-2 brief asked for "real photographs … what a booking costs".
- *Why it matters:* members-only needs "value before sign-in" to pass App Review 5.1.1(v) comfortably and to convert (`2026-09-app-ux.md` §0). NN/g: skip onboarding decks and show the product (https://www.nngroup.com/articles/mobile-app-onboarding/).
- *Proposal:*
  - A slow-moving collage or a single strong photo per category, with example prices ("Plunge saw · €4 / h", "Van · €25 / h", "Photo studio · €160 / h").
  - Keep the three lines.
  - Primary "Create an account" in ivory-on-green (F-6).
  - Reduced motion: a static collage. **UX-30**

**F-29 Sign-in is correct but old-fashioned.**
- *Screenshot:* Welcome back · phone: email + password + "Sign in", with the members-only reason at the bottom, below the demo buttons.
- *Proposal:*
  - Passkeys and the email code first (U-14), with password as an option.
  - The members-only line directly under the title.
  - Sign in / Create account as a text link swap, not tabs.
  - (Local only: the demo buttons are fine.) **UX-31**

**F-30 Onboarding** (read from `Onboarding.tsx`; no fresh account was made).
- One screen: name, person/business, country, district, reason, and the age check. That is short and good.
- *Proposal:* the district picker should offer "Use my location" (asked in context, U-4 style), and there should be a step-2 "Add a photo of yourself". Trust on P2P platforms rises with faces, and the avatar today is initials only. **UX-32**

### 2.11 Localisation layout

**F-31 Mostly clean, with gaps.**
- *Screenshots:*
  - DE · listing · phone: the sticky bar fits, "Anfragen" is fine, and "Werkstatt & Werkzeug" fits.
  - FR · listing · phone: "Remise claire 2", "Conforme à la description 1", and correct espaces before ";" ("Nadia reçoit 13,60 €. … ;"). But the review body stays English ("Handover took five minutes…"), as do the listing titles.
- *Why it matters:* short strings grow the most in translation, 200–300% for strings of 10 characters or fewer (https://www.w3.org/International/articles/article-text-size). French uses U+202F before ; ! ? and U+00A0 before : and inside « » (https://fr.wikipedia.org/wiki/Espace_ins%C3%A9cable). `hyphens: auto` needs the right `lang` (https://developer.mozilla.org/en-US/docs/Web/CSS/hyphens), and `<html lang>` is already set.
- *Proposal:*
  - `hyphens: auto` on body text and headings, with `hyphenate-limit-chars: 8 4 4` for German compounds.
  - A "Translated from English · Show original" affordance on reviews and listing text (machine translation behind a provider seam).
  - Pseudo-loc runs (U-28) at 200% text in each verification round. **UX-33**

### 2.12 Accessibility (beyond what U-30 covers)

- **The page jumps on open** (F-22): a focus-order and orientation problem for screen-reader users too. **UX-25**
- **Dock labels at 10.5 px** (F-4). **UX-5**
- **Focus colour = the action colour = the error colour.** A blue-ink focus ring (3:1 against the page and the plates) separates focus from error (https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html). **UX-6**
- **Chip targets.** The `.tap` pseudo-element gives 44 px vertically, but not horizontally for the 40 px dock "+" (44 × 40): fine at 24 px AA, below the 44 pt HIG. **UX-34**
- **An automated axe run in CI** is still open (U-30). Without it, contrast regressions will creep in as tokens change. **UX-35**

### 2.13 Dark mode and theming readiness

**F-32 Light only.**
- *Why it matters:*
  - Most iOS and Android users run dark at night. A white page in a dark-mode phone is the first "this is a website" tell.
  - Apple: two background sets (base, elevated), semantic colours, 4.5:1 minimum and 7:1 for small text (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/dark-mode.json).
  - `light-dark()` has been Baseline since 2024 (https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark).
- *Proposal:*
  - Tier the tokens (§3), then ship the dark roles in §3.3 behind `prefers-color-scheme` and an Appearance setting (System / Light / Dark). Apple advises against an app-only appearance setting; keep "System" as the default and the override for the web.
  - The status-bar style and `theme-color` follow the theme. **UX-36**

### 2.14 Native feel in the shells

**F-33 Plugins and behaviours missing.**
- *Code:* `package.json` has app, filesystem, preferences, push and share. It has no haptics, status-bar, splash-screen or keyboard plugin.
- *Why it matters:*
  - With target SDK 36, edge-to-edge is enforced and `windowOptOutEdgeToEdgeEnforcement` is disabled. Predictive back is on by default, and `onBackPressed`/`KEYCODE_BACK` are no longer dispatched (https://developer.android.com/about/versions/16/behavior-changes-16).
  - `@capacitor/status-bar` `overlaysWebView`/`backgroundColor` have no effect on Android 16 (https://capacitorjs.com/docs/apis/status-bar).
  - Splash: `launchAutoHide: false`, then hide once the app is ready (https://capacitorjs.com/docs/apis/splash-screen).
- *Proposal:*
  - Add `@capacitor/status-bar` (the style follows the theme and the green welcome plate).
  - Add `@capacitor/splash-screen` (hide after the first render of the route).
  - Add `@capacitor/keyboard` (`resize: native` on iOS, and a `keyboardWillShow` hook to hide sticky bars, U-26).
  - Verify that the existing `backButton` listener still fires under the predictive back on API 36, or move to the `OnBackInvokedCallback`-backed Capacitor path. **UX-37**

**F-34 Overscroll and pull to refresh.**
- `overscroll-behavior-y: none` on the body kills the iOS bounce everywhere, which makes the app feel like a web page.
- *Proposal:* keep the bounce (`contain` on inner scrollers only), and add pull to refresh on Explore, Bookings, Inbox and Notifications with a custom indicator and a haptic tick (https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior). **UX-38**

### 2.15 Consistency

**F-35 Shape has no rule.**
- The radii in use: 2 px (badges), 6, 7, 8 (controls), 10, 12, 14 (cards), 22 (sheet), 24 (panels and bars), 28 (dock), and full (the header CTA, the language switch, the back button, the "+").
- The `Button` doc comment still says "Rectangles, not pills. A 3px radius".
- Two nested tab bars on Bookings ("I booked / I'm hosting" over "Upcoming / Past") share one style.
- *Proposal:*
  - The radius scale in §3.2, with a rule for when a capsule is used (floating chrome and the FAB only).
  - The outer switch on Bookings becomes a segmented control (filled), and the inner one a text tab (underline).
  - Update the stale comments. **UX-39**

### 2.16 Delight

- The booking moment ("Request sent", "Confirmed") is only a banner. **UX-40**
  - A confirmation screen with the listing photo, the time as a big Archivo figure, "Add to calendar" (an .ics file / the native calendar), "Message Nadia", and a success haptic.
  - A single tasteful motion: the plate's time "flips" once, like a split-flap board, which fits the departure-board idea.
- The first published listing gets a celebratory preview ("This is how people see it") and a share sheet. **UX-41**
- Empty states get illustrations in the plate style instead of a 20 px icon. **UX-42**

---

## 3. Design direction

**Keep:**
- the editorial identity;
- the green plate as the "moment" material;
- crimson as the one action colour;
- tabular figures everywhere;
- glass only on floating chrome (dock, sticky bar, sheets over content). This matches Apple's rule: "Don't use Liquid Glass in the content layer" (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/materials.json).

**Change:**
- Bodoni only for words at display sizes;
- a role-based colour system with dark mode;
- a real motion system;
- photo-first content.

### 3.1 Tokens: naming and tiers

Three tiers, in DTCG format (`design/tokens/*.tokens.json`, stable spec
2025.10: https://www.w3.org/community/design-tokens/,
https://www.designtokens.org/tr/drafts/format/). Style Dictionary v4 builds
them into CSS variables and a TS map (https://styledictionary.com/info/dtcg/).
In Figma they are **Variables** with a `Light` / `Dark` mode on the semantic
collection.

- **Primitive**: `color.green.900`, `color.crimson.600`, `size.4`, `duration.150`. No meaning, never used in components.
- **Semantic**: `color.bg.page`, `color.text.primary`, `color.action.primary.bg`, `space.inset.card`, `motion.duration.short`. These swap per mode.
- **Component** (only where needed): `button.primary.bg`, `dock.label.size`, `sheet.radius`.

The CSS names follow the semantic tier: `--color-bg-page`, `--color-text-secondary`
and so on. The current names (`--ink-3`, `--sunken`) get aliased for one
release, then removed. The `check:tokens` script (UX-5) enforces use.

**Type scale** (rem at a 16 px root; follows iOS Dynamic Type, where Body is 17 pt, per the HIG typography table):

| Token | Size / line | Face | Use |
|---|---|---|---|
| `display` | 44 / 46 (phone), 64 / 64 (desktop) | Bodoni 500, opsz 96 | Welcome, Earn hero word |
| `headline` | 34 / 38 | Bodoni 500, opsz 72 | Screen titles (Large Title) |
| `title-l` | 28 / 32 | Bodoni 500 for words; Archivo 600 for user titles | Section heroes, listing title (Archivo) |
| `title-m` | 22 / 28 | Archivo 600 | Sheet titles, card groups |
| `title-s` | 20 / 26 | Archivo 600 | Section heads (replaces t-h3) |
| `body-l` | 17 / 24 | Archivo 400 | Body on phone |
| `body` | 15 / 22 | Archivo 400 | Body on desktop, secondary on phone |
| `label` | 13 / 18 | Archivo 500/600 | Buttons (md), chips, meta |
| `caption` | 11 / 14 | Archivo 600, +0.04em | Eyebrows, dock labels, badges |
| `figure-xl / l / m` | 40 / 28 / 17 | Archivo 600, tabular, lining | Prices, times, ratings |

These are 9 text steps plus figures, and nothing else. Body text is 17 px on the phone, as on iOS.

**Spacing** (4 px base): `space.1`=4, `2`=8, `3`=12, `4`=16, `5`=20 (the phone
gutter), `6`=24, `8`=32, `10`=40, `14`=56, `18`=72. Section rhythm is 40 on the phone
and 56 on the desktop. Card inset 16 / 20.

### 3.2 Radii and elevation

| Token | Value | Use |
|---|---|---|
| `radius.xs` | 4 | Badges, tags |
| `radius.s` | 8 | Chips, inputs, buttons |
| `radius.m` | 14 | Cards, photos, plates |
| `radius.l` | 22 | Sheets, dialogs, floating bars |
| `radius.full` | 999 | Floating chrome only: dock capsule, FAB, avatar |

| Elevation | Light | Dark | Use |
|---|---|---|---|
| `0` | none, a hairline `border.subtle` | none, a hairline | Cards, rows (the ruled system stays) |
| `1` | 0 1 2 rgba(24,33,26,.06), 0 2 8 rgba(24,33,26,.06) | a +4% lighter surface | Hovered card, search pill |
| `2` | 0 8 24 -12 rgba(24,33,26,.30) | a +8% lighter surface, and a 1 px top highlight | Popovers, buy box |
| `3` (glass) | frost 24 px, tint 50–66%, a lit edge, `glass-shadow-raised` | frost 24 px, tint rgba(20,26,21,.62), edge 20% | Dock, sticky bar, sheets |
| `scrim` | rgba(24,33,26,.5) | rgba(0,0,0,.6) | Behind modals |

In dark mode, elevation is expressed by lighter surfaces rather than shadows (Apple base vs elevated backgrounds; Material dark theme: https://m2.material.io/design/color/dark-theme.html).

### 3.3 Colour roles

| Role | Light | Dark | Notes |
|---|---|---|---|
| `bg.page` | #FBFAF8 | #0F1410 | Not pure black |
| `bg.surface` | #FFFFFF | #171D18 | Cards |
| `bg.elevated` | #FFFFFF | #1F2620 | Sheets, popovers (Apple "elevated") |
| `bg.sunken` | #F2F0EB | #0B0F0C | Fills, skeleton base |
| `bg.plate` | #20311E | #1F3A24 | The "moment" material; a touch lighter in dark mode so it still reads as a plate |
| `text.primary` | #18211A | #EEF0EA | |
| `text.secondary` | #39423A | #C3C9BF | |
| `text.tertiary` | #5A6157 | #9AA396 | ≥ 4.5:1 on page |
| `text.on-plate` | #F4F3EE | #F4F3EE | |
| `border.subtle` | rgba(24,33,26,.14) | rgba(238,240,234,.12) | |
| `border.strong` | rgba(24,33,26,.30) | rgba(238,240,234,.28) | Inputs ≥ 3:1 |
| `action.primary.bg` | #8B0D1A | #E0525F | Desaturated and lighter in dark for 4.5:1 with dark text |
| `action.primary.fg` | #FFFFFF | #1A0507 | |
| `action.on-plate.bg` | #F4F3EE | #F4F3EE | The primary on green plates (F-6) |
| `focus.ring` | #2D6479 | #8CC3D6 | Distinct from action and danger |
| `danger` | #C4312B | #FF8A80 | Distinct from crimson |
| `warning` | #8A5200 | #F0B45C | |
| `success` / `money.positive` | #2C6048 | #7CC4A0 | Earnings, "paid", ticks |
| `info` / `idle` | #2D6479 | #8CC3D6 | Free time |
| `badge.bg` | #8B0D1A | #E0525F | |

Every text pair is checked in CI (the axe job, UX-35) in both modes.

### 3.4 Motion tokens

Durations follow M3 (https://raw.githubusercontent.com/material-components/material-components-android/master/docs/theming/Motion.md) and NN/g's 100–400 ms band.

| Token | Value | Use |
|---|---|---|
| `duration.instant` | 100 ms | Press, toggle, chip select, colour change |
| `duration.short` | 150 ms | Hover, tooltip, toast out |
| `duration.medium` | 250 ms | Sheet and dialog in, tab crossfade, card expand |
| `duration.long` | 350 ms | Push/pop screen, hero morph, map sheet snap |
| `duration.xlong` | 500 ms | The one celebratory moment (booking confirmed) |
| `easing.standard` | cubic-bezier(0.2, 0, 0, 1) | Default (already `--ease-out`) |
| `easing.decelerate` | cubic-bezier(0.05, 0.7, 0.1, 1) | Things entering (M3 emphasised decelerate) |
| `easing.accelerate` | cubic-bezier(0.3, 0, 0.8, 0.15) | Things leaving; exits take 2/3 of the entry time |
| `spring.spatial` | damping 0.9, stiffness 700 (≈ `linear()` curve in CSS) | Sheet drag release, dock indicator |
| `spring.effects` | damping 1.0, stiffness 1600 | Opacity and colour, no overshoot |

Rules:
- Only `transform` and `opacity` animate.
- Exits are faster than entries.
- Never animate on every list item (keep the "one orchestrated entrance" rule).
- **Reduced motion:** swap slides for 100 ms fades and never animate blur, as Apple advises. This is instead of today's global `1ms !important`, which also kills useful fades (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/accessibility.json).
- The drop in `--ease-spring` (1.4 overshoot) is retired: M3 says spatial springs bounce only slightly.

### 3.5 Components to improve

| Component | Change |
|---|---|
| `Button` | Sizes lg 52 / md 44 / sm 36 (the sm keeps a 44 px tap area). A press state (scale .98, 100 ms). A loading state with an inline spinner, the label kept and the width fixed. A disabled state per F-6. An `on-plate` variant. |
| `Sheet` | Drag and detents, exit animation, a dialog at ≥ 768 px, a grabber that is a button, focus behaviour kept (F-8). Footer bar respects the keyboard. |
| `ListingCard` | One component in `grid` and `row` densities. The photo with a blur placeholder. The title in 2 lines of Archivo. Rating, distance, "Free from 19:30", and the price with its unit. The heart is optimistic with a haptic. |
| `Chip` | Filter chip (removable, ×) vs choice chip (selected fill). 36 px visual, 44 px target. |
| `Segmented` | Split into `SegmentedControl` (a filled capsule track, for mode switches) and `Tabs` (underline, for sections). |
| `PriceSummary` (new) | One component for the listing bar, the buy box, the confirm sheet and the booking detail: line items, the fee under one name, the total, and the policy line. Money in Archivo figures only. |
| `SlotPicker` (new) | A day strip plus grouped times plus a duration stepper. Used by the listing, the buy box popover and search "When". |
| `ThreadRow` / `MessageBubble` (new) | Inbox rows. Bubbles with pending, sent and failed-with-retry states, report on long-press or an overflow button. |
| `SettingsRow` (new) | An icon, label, value and chevron, or a switch. Grouped lists with an inset style. |
| `Toast` | Enter from below and exit down (150 ms). An optional action ("Undo", "View"). Stacks above the keyboard. |
| `Skeleton` | Keep the layout-shaped approach. Show it only after 300 ms, so fast loads never flash (NN/g: no indicator under 1 s, a skeleton for 2–10 s page loads: https://www.nngroup.com/articles/skeleton-screens/). |
| `Avatar` | Photo when present. Initials on a colour picked from the name hash, not always sunken grey. A verified tick overlay. |
| `Badge` (verification) | Says what was checked: "ID checked", "Email", "Business · VAT checked" (U-32). |

### 3.6 Key screen redesigns (concrete enough to build)

**Explore (phone)**
1. Top: the "Cappy" wordmark left, the district picker right (as now).
2. A composite search pill, 56 px, elevation 1: "What do you need?" / "Any time · Kreuzberg + 10 km". A tap opens a full-screen search with three steps (What, When, Where) and a "Show 31 results" footer.
3. The category rail with 24 px icons over labels (Airbnb-style), selected with an underline. It is sticky under the pill when scrolled.
4. "Free in the next 24 hours": a horizontal rail of `ListingCard grid` at 280 px, not one hero plus a grid.
5. "Near you" and "Popular this week" sections, then "What do you need?" as today.
6. A floating "Map" pill button, bottom centre, above the dock.

**Explore (desktop)**
- The search bar sits in the top bar as an expanding capsule (What · When · Where), under the nav.
- The category rail spans the width.
- Results as a 4-column grid, or a 60/40 list-map split when the map is on. The map uses price pins and "Search this area".

**Listing (phone)**
- The dock is hidden.
- A full-bleed gallery, 4:3, swipe, "1 / 5", with the back and heart as glass buttons.
- Title (Archivo 28/600), meta line (★ 4.8 · 4 reviews · Tempelhof · 4 km).
- Owner row (photo, name, verified badge, "Replies in ~1 min"), tappable to a profile.
- Highlights (3 icon rows: instant book or by request, the policy in one line, the hand-over).
- Description, the week chart, "What's included", reviews (a translated flag), location (a district map tile), rules, report.
- The bottom bar docks to the edge: "€16.00 total · Sat 10:30–14:30" (the time line is tappable to change it) and a "Request" button.

**Listing (desktop)**
- A gallery mosaic across the full width.
- Below it, a 2-column layout: content on the left; on the right a sticky buy box with Day, Start and Duration fields, the `PriceSummary`, "Request", and "You won't be charged yet".

**Booking flow**
1. Tap "Request" to open the review sheet (medium detent): the listing row, When (editable), the `PriceSummary`, the policy line, the payment method (the saved card, or the Stripe Element inline, themed, with Apple Pay / Google Pay above), the message to the owner (optional, prefilled "Hi Nadia, …"), and the button "Request and hold €16.00".
2. A success screen (UX-40): the plate with the time, "Nadia usually replies in ~1 min", "Message", "Add to calendar", "Done". Then land on the booking.

**Booking detail**
- Header: a small photo, the title, and the state as a big word ("Confirmed") with a countdown ("Starts in 21 h").
- One contextual primary in the bottom bar (per F-22); secondary actions in "⋯" (Change, Cancel, Report, Help).
- Sections: Hand-over (address after acceptance, map, access notes), With Nadia (avatar, "Message", "Call" masked if ever added), Your money (`PriceSummary` and refunds), Photos, Safety tips (collapsed after the first read), Help with this booking.

**Inbox**
- Tabs: All / Unread.
- `ThreadRow`: avatar, name, the listing thumb, the last message, time, an unread dot, and a status chip ("Request · 23 min left").
- The thread screen: a booking card pinned at the top (with its primary action), the bubbles, and a composer that follows the keyboard. The safety banner as today.

**Earn** (the "Today" pattern)
- "Needs you" (requests with a countdown ring), "Today" (hand-overs), "Money" (earned, on the way, next payout date, "Set up payouts" if missing).
- "Your listings" as `ListingCard row` with the owner's photo, the status (Live / Under review / Paused), and "Edit" in an overflow.
- The idle chart moves inside each listing.

**AddListing**: the 5 steps in F-24, with a progress bar under the header and one primary "Next" in the bottom bar.

**You / Profile**: an identity header (photo, name, verified badges, "View profile"), then grouped rows: Account (Personal info, Verification, Payments and payouts), Preferences (Notifications, Language, Appearance), Support (Help, How Cappy works, Report a problem), Legal, Privacy (Download my data, Delete account), then Sign out and Sign out everywhere.

**Staff console**: in F-13.

---

## 4. What could not be reviewed

- **Real devices.** The iOS and Android shells were not run. Safe areas, the status bar, the keyboard, haptics, predictive back, Dynamic Type and wallets were judged from code and the 390 px iframe. R2-10 covers a device pass.
- **Onboarding** was read from code only; a fresh account would have been needed.
- **The payment step**: the Stripe Element and the fake provider were not opened, since that needs a booking. Its look is judged from `PayStep.tsx`.
- **Booking detail states beyond "confirmed"** (requested, in progress, disputed, completed, cancelled) were not opened. There were no bookings in those states for the demo buyer and host 2 in this session, and none were created. The findings in F-22 apply to the component as a whole.
- **Timing of the screen entrance fade.** In the iframe, several screenshots caught screens at partial opacity 3–4 s after navigation, while a JS probe then found `opacity: 1` and no running animation. This looks like capture throttling rather than a real 4 s fade, so it is not reported as a finding. A device check should confirm it.
- **Research sources.** Pages for Vinted's buyer protection, Turo's checkout, Revolut's motion and Airbnb's total-price article could not be fetched this session. The claims about them rest on the sources in `2026-09-app-ux.md`, or on the verified Baymard and NN/g figures, and are not re-cited here.

---

## 5. Checklist (prioritised)

**P0** blocks a top-tier launch. **P1** comes soon after. **P2** is polish. Within each band the most impactful items come first.

### P0

- [ ] UX-1 [web]+[design] Photos that show the listed thing: category-true seed photos never reused in one viewport; with no owner photo, a designed category illustration with the listing name instead of unrelated stock — https://www.nngroup.com/articles/trustworthy-design/
- [ ] UX-4 [web]+[design] Bodoni only for words ≥ 28 px; every price, time, rating, count and user-written title in Archivo tabular (`figure-*` tokens), so "€3.40" and "1.4 m" can't be misread — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/accessibility.json
- [ ] UX-12 [web]+[app] An Inbox destination (threads per booking, unread, status chip, thread screen with the booking card pinned); dock becomes Explore · Bookings · Inbox · Earn · You and "+" moves into Earn and the desktop bar — https://news.airbnb.com/airbnb-2025-summer-release/
- [ ] UX-15 [web] A "When" in search: a day strip, a start hour and a duration in a composite What · When · Where search (a full-screen step sheet on the phone, popovers on the desktop); results priced for that window — https://www.nngroup.com/articles/mobile-faceted-search/
- [ ] UX-23 [web] Renter's confirm sheet and `PriceSummary`: price × hours, the service fee, the total, the policy as a dated line, and the payment method; no "host receives" line for the renter; the button names the amount ("Request and hold €16.00"; DE §312j wording kept) — https://baymard.com/lists/cart-abandonment-rate
- [ ] UX-25 [web] Booking detail: the primary action follows the clock (message and directions before, "collected" only from 30 min before, "hand back" after); destructive actions in an overflow; a status header with a countdown; the chat scroll never scrolls the page (`Conversation.tsx:105`) — https://www.nngroup.com/articles/error-message-guidelines/
- [ ] UX-3 [web]+[backend] Image loading: a dominant-colour or blurhash placeholder per photo, `fetchpriority="high"` on the LCP image, `width`/`height` + `sizes` on every image, a hidden alt text on failure (with U-40) — https://web.dev/articles/fetch-priority · https://web.dev/articles/optimize-cls
- [ ] UX-2 [web] Listing gallery: swipe on the phone, a mosaic on the desktop, full screen with pinch, "n / N", alt "Photo n of N, {title}" — https://baymard.com/research/product-page
- [ ] UX-13 [web]+[app] Detail routes on the phone (`/listing/:id`, `/bookings/:id`, `/earn/new`, `/earn/edit/:id`) hide the dock; the action bar docks to the bottom edge with the safe area and hides while an input is focused — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- [ ] UX-9 [web]+[app] `Sheet`: drag to dismiss (30% or velocity), medium and large detents, a grabber as a button, an exit animation, and a centred dialog (or side sheet for Filters) at ≥ 768 px; the close button stays — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/sheets.json
- [ ] UX-6 [design]+[web] Colour roles: split action (crimson), danger (#C4312B), money-positive (green), badge and focus (blue ink #2D6479); no money in crimson — https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- [ ] UX-5 [design]+[web] Tier the tokens (primitive → semantic → component) in DTCG `.tokens.json`, built with Style Dictionary into CSS variables; replace the 21 ad-hoc `text-[…rem]` sizes and the stray radii with the §3 scale; a `check:tokens` script fails on literals outside `ui.tsx`; dock labels 11 px/600 — https://www.designtokens.org/tr/drafts/format/ · https://styledictionary.com/info/dtcg/
- [ ] UX-20 [web] Desktop buy box with Day, Start and Duration fields (and the phone bar's time line opens the same picker); tapping a free bar in the week chart sets it — https://baymard.com/research/product-page
- [ ] UX-24 [web]+[app] Payment: Stripe Appearance API with Cappy tokens, an enclosed card panel with a lock and "Payments by Stripe · held, not charged", Express Checkout (Apple Pay / Google Pay) on the web, and wallets tested or hidden in the shells — https://baymard.com/blog/perceived-security-of-payment-form
- [ ] UX-30 [web]+[design] Welcome shows the product: category photos with example prices ("Plunge saw · €4 / h"), a static version under reduced motion, and the primary in ivory on the green plate — https://www.nngroup.com/articles/mobile-app-onboarding/
- [ ] UX-36 [design]+[web]+[app] Dark mode: the §3.3 roles in both modes via `prefers-color-scheme` / `light-dark()`, an Appearance setting (System default), `theme-color` and the shell status bar following it; contrast checked in both — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/dark-mode.json · https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark
- [ ] UX-37 [app] Shell plugins: `@capacitor/status-bar`, `@capacitor/splash-screen` (`launchAutoHide: false`, hidden after first render), `@capacitor/keyboard` (hide sticky bars on `keyboardWillShow`); verify the back handler under predictive back at target SDK 36 — https://developer.android.com/about/versions/16/behavior-changes-16 · https://capacitorjs.com/docs/apis/splash-screen
- [ ] UX-35 [web] axe-core in CI over every route in both themes, EN/DE/FR, at 390 px and 1440 px (closes U-30) — https://www.w3.org/TR/WCAG22/

### P1

- [ ] UX-8 [web] Motion system: the §3.4 tokens; a push/pop slide for drill-down routes on the phone, a crossfade between tabs, exits at 2/3 of entry time, press states (scale .98, 100 ms), and reduced motion as short fades instead of a global 1 ms — https://www.nngroup.com/articles/animation-duration/ · https://raw.githubusercontent.com/material-components/material-components-android/master/docs/theming/Motion.md
- [ ] UX-11 [app] Haptics helper (web no-op): selection on slot, day and chip picks; light impact on the heart; success on request sent, booking accepted and listing published; warning on a refused payment — https://capacitorjs.com/docs/apis/haptics
- [ ] UX-10 [web] Optimistic UI for the heart, chat messages (pending → sent → failed with retry) and settings toggles, via `useOptimistic`; never for money — https://react.dev/reference/react/useOptimistic
- [ ] UX-16 [web] A real map: vector tiles, clustering price pins at district precision, a list/map split at ≥ 1024 px, a full-screen map with a draggable results sheet on the phone, "Search this area" — https://www.nngroup.com/articles/mobile-faceted-search/
- [ ] UX-17 [web] One `ListingCard` in grid and row densities for home, results and categories: 2-line titles, rating, "free from", the price with its unit; radius steps chosen per unit (mi vs km) — https://baymard.com/research/product-page
- [ ] UX-18 [web] Applied filters: one removable chip per value plus "Clear all" (closes U-21) — https://baymard.com/blog/how-to-design-applied-filters
- [ ] UX-19 [web] AddListing in 5 steps (Photos and name · Where · When · Price with a live "You earn" · Rules and review), a progress bar, "Save and exit", "Publish" only on the review, at least 3 photos with shot hints — https://baymard.com/blog/checkout-flow-average-form-fields
- [ ] UX-21 [web] `SlotPicker`: a day strip with free-hour dots, times grouped Morning / Afternoon / Evening, taken times shown disabled with a reason instead of gaps — https://www.nngroup.com/articles/errors-forms-design-guidelines/
- [ ] UX-22 [web] One name for the fee in every language ("Cappy service fee" / "Cappy-Servicegebühr" / "frais de service Cappy"), on the listing, the sheet, the booking and invoices — https://www.nngroup.com/articles/trustworthy-design/
- [ ] UX-26 [web] Earn "Today": needs you, today's hand-overs, and real money (earned, on the way, next payout); idle time as an invitation with no hypothetical euro total — https://www.nngroup.com/articles/trustworthy-design/
- [ ] UX-27 [web] Profile as grouped settings rows (Account · Preferences · Support · Legal · Privacy), Notifications as a screen of switches, Sign out last, "Earned" hidden for non-hosts, the "How Cappy works" essay moved to Help — https://support.google.com/googleplay/android-developer/answer/13327111
- [ ] UX-7 [web] States: disabled = sunken fill + tertiary text; validate on press where possible; a loading state with a fixed width and an inline spinner — https://baymard.com/blog/inline-form-validation
- [ ] UX-14 [web] Staff shell: its own rail (Cases, Reports, Held, Refund approvals, Audit), full width, queue tables with age and SLA, a split detail pane, j/k/Enter shortcuts, full ids with copy, no consumer CTA — https://www.nngroup.com/articles/response-times-3-important-limits/
- [ ] UX-33 [web] Localisation layout: `hyphens: auto` with `hyphenate-limit-chars`, a U+202F/U+00A0 check in `check:i18n` for FR, "Translated · Show original" on reviews and listing text (a provider seam) — https://www.w3.org/International/articles/article-text-size · https://fr.wikipedia.org/wiki/Espace_ins%C3%A9cable
- [ ] UX-38 [app]+[web] Keep the native bounce (`overscroll-behavior: contain` only on inner scrollers) and add pull to refresh with a haptic tick on Explore, Bookings, Inbox and Notifications — https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior
- [ ] UX-39 [design]+[web] Shape rules: the §3.2 radius scale, capsules only for floating chrome and the FAB; Bookings' outer switch as a filled segmented control and the inner as underline tabs; stale doc comments in `ui.tsx` fixed — https://karrisaarinen.com/dls/
- [ ] UX-31 [web] Sign-in: the members-only line under the title, passkeys and the email code first (with U-14), and Sign in / Create account as a link swap — https://www.w3.org/TR/WCAG22/#accessible-authentication-minimum
- [ ] UX-40 [web]+[app] A booking-confirmed moment: a success screen with the photo, the time as a big figure, "Add to calendar" (.ics), "Message", a success haptic, and one split-flap "flip" of the time plate (static under reduced motion) — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/motion.json
- [ ] UX-28 [web] Notifications: an icon or thumbnail per type, an unread dot, Today / Earlier groups, a 2-line clamp, and swipe to mark read with a button alternative — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/

### P2

- [ ] UX-29 [web] Help: search, "Help with this booking" at the top when a booking is active, and a `?` in the same header position on every screen (WCAG 3.2.6) — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- [ ] UX-32 [web] Faces: an optional profile photo in onboarding and Profile; avatars show photos, or initials on a name-hashed colour; a verified tick overlay; the verification badge names what was checked — https://www.nngroup.com/articles/trustworthy-design/
- [ ] UX-34 [web] Target sizes: the dock "+" and the chips at 44 × 44 pt (HIG) and 48 dp (Material) with 8 dp spacing, not only 24 px AA — https://support.google.com/accessibility/android/answer/7101858
- [ ] UX-41 [web] First published listing: a "This is how people see it" preview and a share sheet — https://www.nngroup.com/articles/empty-state-interface-design/
- [ ] UX-42 [design] Empty-state and category illustrations in the plate style (also used by UX-1's no-photo fallback) — https://www.nngroup.com/articles/empty-state-interface-design/
- [ ] UX-43 [design] A Figma library mirroring the tokens (Variables with Light/Dark modes) and the §3.5 components, published so design and code share names — https://www.w3.org/community/design-tokens/
- [ ] UX-44 [web] Skeletons shown only after 300 ms, and spinners only for in-place module loads — https://www.nngroup.com/articles/skeleton-screens/
- [ ] UX-45 [web] Core Web Vitals field monitoring (the `web-vitals` library into the existing analytics seam), p75 LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 per route, on phone and desktop separately — https://web.dev/articles/vitals · https://web.dev/articles/optimize-inp

---

## 6. UI/UX criteria for docs/READINESS.md

Proposed for the agent that owns READINESS.md. Each is scored 1–5 and checkable.

1. **Imagery truth.** Every listing on Explore and the listing pages shows the owner's photo of the listed thing, or a designed fallback; no unrelated stock; a gallery exists.
2. **Type legibility.** No price, time, rating or model number in the display serif; every text size comes from the token scale (`check:tokens` passes).
3. **Token system.** Tiered DTCG tokens are the only source of colour, type, space, radius and motion; light and dark modes; a Figma library in sync.
4. **Contrast and accessibility.** axe is clean on every route in both themes and all three languages at 390 and 1440 px; targets ≥ 44 pt; focus is visible and distinct from error; reduced motion is respected.
5. **Price clarity.** The same `PriceSummary` everywhere; the total shown before the button; one fee name; the policy as a dated line; nothing about the host's money in the renter's flow.
6. **Search completeness.** What, When and Where all searchable; the applied filters visible and removable; a real map with price pins.
7. **Navigation model.** An Inbox destination; detail screens own the bottom edge on the phone; staff have their own shell.
8. **Motion and feedback.** Motion tokens are used; sheets are draggable with detents; press states on every control; optimistic UI for non-money actions; haptics in the shells.
9. **Perceived performance.** Field p75 LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 on phone and desktop; image placeholders; no layout jumps on open.
10. **Native feel.** Status bar, splash, keyboard and back all handled on real iOS and Android 16 devices; the native bounce and pull to refresh work.
11. **Consistency.** One card component, one sheet, one set of state styles; a design review signs off each key screen against §3.6.
12. **Localisation layout.** No truncated verbs or overflow in DE/FR at 200% text; French punctuation spacing correct; hyphenation on; the original language of user text labelled.

---

# Round 2 (2026-09-26, at `7ef8bf1`)

The UI/UX lead's second pass, after the first UX build (`1daf0da`, `0a74b1c`).
It re-scores round 1's areas, checks every UX-n in the browser, lists what the
build got wrong, and proposes UX-46 onwards. It proposes and changes no code.

**How the screens were seen.**
- Browser: Chrome on `http://127.0.0.1:5173`, signed in with the demo buttons as buyer, host 2 and staff.
- Desktop: a 1440 px window.
- Phones: same-origin iframes at 390×844, 375×667, 360×800 and 430×932, side by side and scaled to fit. A window resize could not go below the desktop width.
- Themes and text size: light and dark (via the Appearance setting), and 100 % and 200 % text (the root font size set to 200 % inside each frame, the way the app's own large-text probe reads Dynamic Type).
- Languages: EN, DE and FR.
- Checks: a scripted audit ran in every frame on Explore, Listing, Bookings, Inbox, Earn, You and Notifications. It measured text contrast against the composited background, targets under 44 px, values off the 4 px grid, accent-filled elements, truncation and horizontal scroll, against `.claude/skills/cappy-ui/SKILL.md` §7.
- **Safe area:** `env(safe-area-inset-*)` cannot be simulated in an iframe. It was checked in code: the dock has none (R2-F2).
- **Data changed:** one request booking as host 2 on the Festool saw (`bk_01m3fgk1w1368s45kxgmp9rh16`, "waiting for Nadia"), so that the pay path, the booking page and the Inbox could be seen. No message was sent.
- **Owner feedback** (via the coordinator) was treated as P0: "the dark mode is a bit bad, and it needs to be easy to change to light mode". Their screenshot of the phone dock in dark was also reviewed.

**GIFs** (`gif_creator`, saved to `~/Downloads`, not in the repo):
- `cappy-r2-explore-to-booking-phone-dark-en.gif`: search "saw" → listing → confirm sheet → drag the sheet away.
- `cappy-r2-gallery-fullscreen-phone-dark-en.gif`: the gallery → full screen → next → Esc.
- `cappy-r2-inbox-empty-after-request-phone-dark-en.gif`: the empty Inbox, the buyer's Bookings and You, sign-out, host 2's request → booking page → the Inbox still empty.
- `cappy-r2-filters-dialog-and-map-desktop-light-en.gif`: category → the Filters dialog → When "Tomorrow" → the "map".
- `cappy-r2-dark-mode-toggle-and-explore-phone-en.gif`: You → Appearance Light → Dark → Explore.

**Before screenshots** (the scratchpad, for the builder): `r2-before-earn-dock-390-dark.png` and `r2-before-earn-dock-390-light.png`.

## R2.1 Scores, round 1 → round 2

| Area | R1 | R2 | Why (round 2) |
|---|---|---|---|
| Visual hierarchy and identity | 3 | 3 | Archivo titles and figures make listings readable. But the first thing on Explore is still smokestacks for a 3D printer. The phone dock (six slots and a crimson disc) is now the loudest thing on every screen. |
| Typography | 2 | 3 | Prices, times, ratings and user titles are Archivo tabular (UX-4 verified). Still wrong: dock labels are 10.5 px; phone body runs 13 and 15, not the rulebook's 17; Bodoni hairlines break up in dark at 28 px ("No messages yet"); "Earn" breaks mid-word at 200 % text. |
| Spacing and layout | 3 | 3 | Consistent 20 px gutter. Off the 4 px grid in every screen: 3, 5, 6, 10 and 14 px gaps and paddings. The desktop mosaic leaves a hole when a listing has 2 photos. Desktop text-search results are 56 px rows across 1,110 px. |
| Colour and contrast | 3 | 3 | The roles are split, and `check:contrast` passes 40 pairs in both themes. The audit found no text under 4.5:1 on solid surfaces. But crimson now also fills the "Sold" bars; amber (warning) carries reassurance ("Nothing is charged yet"); hairlines are 1.33:1 light / 1.35:1 dark (rule 1.5). |
| Imagery | 1 | 2 | Real gallery, n / N, no photo twice in a grid, designed plates. But the demo data still shows the wrong stock photos (the grid-claim rule keeps the *wrong* photo and plates the others). Stock images get no colour placeholder. Photos are not dimmed in dark. The full-screen viewer is ivory in dark. |
| Iconography | 3 | 3 | Unchanged. The active tab has no filled variant. |
| Motion and feedback | 2 | 3 | Push/pop on phones, a tab crossfade, the hero morph, sheets that drag between detents and leave, exits at ⅔. Browser/hardware Back skips the pop transition; no haptics; no optimistic UI. |
| Navigation | 3 | 3 | Inbox is a destination, and detail screens hide the dock. But the dock keeps the "+" (six slots), the notifications badge sits on "You", a thread opens inside the booking page, and a request makes no thread until someone writes. |
| Forms and input | 3 | 3 | Unchanged: AddListing is one 3,092 px page with "Publish listing" pinned. Disabled primaries are still 30 % crimson. |
| Search and discovery | 2 | 2 | A day and a start hour exist, but only inside the category Filters dialog (15 wrapping day chips next to a contradicting "Needed within"). The chosen day is not shown in the applied chip. Text search has no filters. The map is still the radial diagram. |
| Booking and checkout | 3 | 3 | `PriceSummary` is clear: line × hours, total, fee named once, a dated policy. But on a request listing the button says "Book and pay · €16.00" ("Zahlungspflichtig buchen") right under "Nothing is charged yet". There's no payment-method row and no success moment, and the sticky bar on the new booking is "Withdraw". |
| Trust and safety | 3 | 3 | Unchanged. The badge doesn't say what was checked. There's no rating distribution and no host replies, and listing text in DE/FR is not labelled as untranslated. |
| Empty, error, offline | 4 | 4 | Good. But the Inbox empty state has no action. |
| Perceived performance | 2 | 3 | `fetchpriority="high"` on the hero, `width`/`height`/`sizes` everywhere, renditions with a colour for uploads. No prefetch on hover or viewport, no optimistic UI. The hero can morph into a skeleton. |
| Accessibility | 3 | 3 | Sheets trap and return focus, and the gallery dialog focuses Close. But focus stays on `<body>` after a route change. There's no live region until a toast. The gallery lacks APG carousel semantics. The unread dot is `aria-hidden` with no text. 14–29 targets under 44 px per screen. |
| Consistency | 2 | 2 | Three result layouts still. Two accent fills on most screens (the dock "+" and the page's primary). Chips are capsules on Explore and 8 px on the slot picker. |
| Dark mode and theming | 1 | 2 | It exists, follows the system, and is set before first paint. It is not yet good, and the owner says so: surfaces 1.09–1.2:1 apart, a darker-than-page "sunken", a near-black active pill, a see-through dock, an ivory lightbox, undimmed photos, and the switch buried at the bottom of You. |
| Native feel | 2 | 2 | The dock ignores the bottom safe area. No haptics, status-bar, splash or keyboard plugins. |
| Delight | 2 | 2 | No confirmed-booking moment. The Earn hero still guilts ("€1,428.75 of time nobody is paying you for"). |
| Staff console | 2 | 2 | Unchanged consumer shell with "List capacity". |

**Overall: 2.5 → about 2.8.** The build fixed the data-legibility problems and
added the missing structures (inbox, gallery, sheets, dark tokens). The new
chrome, the dock and dark mode, is now the weakest craft on screen. The P0 list
below (UX-46 … UX-54) is what takes it to about 3.5.

## R2.2 Round 1 items: verified status

"Done" means seen working in the browser; "partial" says what is left.

| Item | Status | Evidence / what is left |
|---|---|---|
| UX-1 | partial | The code rule works (no photo twice, plates). The demo seed still shows a smokestack for the Bambu printer and an electrician for the Festool saw, first on Explore and in search → UX-53 |
| UX-2 | partial | Phone swipe, n / N, full screen, alt "Photo n of N". But the viewer is ivory in dark; the sticky price bar and the back button paint over it and hide the counter; the desktop mosaic leaves a hole with 2 photos; no carousel semantics → UX-49, UX-56 |
| UX-3 | partial | `fetchpriority`, `sizes`, `width`/`height` verified. Placeholders are a flat `--sunken` for all non-upload images (demo) → UX-69 |
| UX-4 | done | Titles, prices, times and ratings in Archivo; "1.4 m" and "€4.00" read correctly |
| UX-5 | partial | `check:tokens` passes. Dock labels are 10.5 px (rule 11). Off-grid 3/5/6/10/14 values. No DTCG file → UX-64 |
| UX-6 | done | Money in green ("Earned €0.00"), focus blue, danger apart from crimson. New misuse → UX-61 |
| UX-7 | not done | Disabled "Sign in" and "Send" are still 30 % crimson: 1.46:1 against the page in dark, text 1.49:1 |
| UX-8 | partial | Push/pop and crossfade work via `useNav`. Browser Back / Android back (popstate) cut without the pop → UX-58 |
| UX-9 | done | Drag to dismiss (verified), detents, a grabber button, the desktop dialog (verified on Filters), exit animation |
| UX-10 | not done | No `useOptimistic` or `onMutate` in the code |
| UX-11 | not done | No haptics helper or plugin |
| UX-12 | partial | Inbox tab, server unread, All/Unread. But the "+" is still in the dock; no thread screen (a row opens `/bookings/:id#messages`); no thread until the first message; empty state without an action → UX-46, UX-52 |
| UX-13 | done | Dock hidden on listing, booking and add routes. The bar floats as a capsule with content visible below it; fine, but see UX-46 for the safe area |
| UX-14 | not done | `/admin` unchanged |
| UX-15 | partial | Day and start hour in the category Filters dialog, honoured by results. No composite What · When · Where; text search has none; the chosen day is missing from the applied chip → UX-55 |
| UX-16 | not done | The radial diagram remains |
| UX-17 | not done | Three result layouts; truncated rows with no rating; 75 km shown as "47 mi" |
| UX-18 | not done | One merged "2 hours · 47 mi" chip |
| UX-19 | not done | One 3,092 px page |
| UX-20 | partial | Desktop Day / Starts / Duration selects work. On the phone the bar's time line is not tappable, and the week chart does not set the time |
| UX-21 | not done | 22 ragged time chips, 15 day chips on 3 rows |
| UX-22 | partial | "service fee" on the listing and sheet, but "Cappy fee" remains in 3 strings (`src/app`) |
| UX-23 | partial | `PriceSummary` verified. The button copy contradicts the request flow, and there's no payment-method row → UX-50 |
| UX-24 | partial | Stripe `appearance` from tokens (code). No Express Checkout Element; the pay step was not shown on the demo path |
| UX-25 | partial | The chat scrolls its own box (code). But the only sticky action on a fresh request is the destructive "Withdraw from this booking"; no countdown header → UX-51 |
| UX-26 | not done | Hypothetical euro total still the hero |
| UX-27 | not done | Profile is still one long page; Appearance is the 11th section |
| UX-28 | partial | An unread dot exists. No icons or groups; rows say "The details are in the app" inside the app; the dot is `aria-hidden` → UX-62 |
| UX-29 | not done | Help has no search |
| UX-30 | partial | Ivory primary on green, example prices as chips. No photographs |
| UX-31 | not done | Tabs, password first, the disabled crimson button |
| UX-32 | not done | Initials on `--sunken` |
| UX-33 | partial | `hyphens: auto` on headings only, and it breaks 4-letter words at 200 % ("Ear / n"). Body `hyphens: manual`. No "Translated" label → UX-54 |
| UX-34 | not done | Dock "+" 44×40; chips 36 high; heart 36×36; back 40×40; the rating link 56×22; profile checkboxes 20×20 |
| UX-35 | not done | No axe |
| UX-36 | partial | Themes work and follow the system. Quality defects → UX-47, UX-48 |
| UX-37 | not done | Plugins not installed |
| UX-38 | not done | `overscroll-behavior-y: none` still on the body |
| UX-39 | partial | `check:tokens` shows radius literals at 0. The Bookings switch and the Inbox tabs share one underline style; chips mix capsule and 8 px |
| UX-40 | not done | The request lands straight on the booking page |
| UX-41 | not done | — |
| UX-42 | partial | Category plates exist. Empty states still use a 20 px icon |
| UX-43 | not done | — |
| UX-44 | done | Skeletons after 300 ms (code `edd0521`; not timed in the browser) |
| UX-45 | not done | No `web-vitals` |

Round 1: 5 done, 18 partial, 22 not done.

## R2.3 New findings on the built work

**R2-F1 The phone dock: owner's P0.**
- *Screenshots:* Earn · 390 · dark (owner's `10.png` and ours): six slots, 58 px each at 390 and 52 px at 360. The measured parts:
  - a 44×40 crimson disc in the middle;
  - the active tab a `--sunken` (#0b0f0c) lozenge on a 55 % dark glass, **1.08:1** against the bar;
  - the notifications badge "7" on "You", clipped by the capsule's top edge at 100 % and cut in half at 200 %;
  - labels 10.5 px `ink-4`: 5.8:1 over the page, but as low as **1.4:1** where white text scrolls under the glass;
  - "Bandsaw and bench…" and the amber "Payout on hold" readable through the bar, in light too.
- *Why it matters:*
  - HIG: "Use a tab bar to support navigation, not to provide actions." Reserve badges for critical information. Label with single words. Tab bars minimise on scroll in iOS 26 (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/tab-bars.json).
  - M3: 3–5 destinations. The active indicator is a 56×32 capsule in `secondaryContainer`, the bar is 80 dp (64 in Expressive) on `surfaceContainer` (https://raw.githubusercontent.com/material-components/material-components-android/master/docs/components/BottomNavigation.md).
  - The rulebook (§4 Dock) already says at most 5, no floating create button, and an opaque bar.
- *Comparison* (own observation of the current apps; their pages could not be fetched this session):

  | App | Items | Create in the bar? | Active state | Background |
  |---|---|---|---|---|
  | Airbnb | 5: Explore, Wishlists, Trips, Messages, Profile | No. Hosting is a mode switch in Profile | Brand-tinted filled icon and label | Opaque white with a hairline |
  | Vinted | 5, with "Sell" as a labelled tab | Yes, but as an ordinary labelled tab, not a disc | Tinted icon | Opaque |
  | Revolut | 5 | No; actions sit in the Home header | Filled icon | Blurred, dense |
  | Instagram (2025) | 5 | Moved out of the bar into a header "+" | Filled icon, no label | Opaque |
  | Apple (iOS 26 Music, Photos) | 3–5 | No; actions are toolbar buttons | A glass lozenge, tinted | Liquid Glass capsule that minimises on scroll, with a separate search button |

  Cappy's disc copies none of them. It is the old iOS 6 "raised centre tab", and it is also the second accent fill on every screen.
- *Proposal:* **UX-46** (spec below).

**R2-F2 The dock ignores the bottom safe area.**
- *Code:* the nav is `max-md:bottom-0` with no padding. `--dock-h` reserves `56 + 10 + env(safe-area-inset-bottom)` for content, but the bar itself sits on the screen edge.
- *Risk:* on an iPhone the 34 pt home indicator lies across the labels, and the capsule's rounded bottom corners meet the display corner.
- *Proposal:* part of **UX-46**.

**R2-F3 Dark mode surfaces have no steps.**
- *Measured:*
  - page #0f1410 (L\* 5.8, near black);
  - `surface` 1.09:1 and `elevated` 1.20:1 against it;
  - `sunken` #0b0f0c is *darker* than the page, so every image placeholder, input and the old active pill is a hole;
  - `line` 1.35:1 (rule 1.5).
- *Other defects:*
  - Photos are undimmed.
  - Bodoni at 28 px on dark loses hairlines ("yet" reads "yct").
  - Disabled primaries are 1.46:1.
  - The full-screen gallery uses `--inverse` and turns ivory.
  - The content sheet is glass, so the page's crimson bleeds through behind "Not yet".
- *Why it matters:*
  - Material dark: a #121212 base, lighter surfaces for elevation, desaturated colour (https://m2.material.io/design/color/dark-theme.html).
  - Apple: base vs elevated backgrounds, test with Increase Contrast and Reduce Transparency (https://developer.apple.com/tutorials/data/design/human-interface-guidelines/dark-mode.json).
  - web.dev: tone images down in dark (https://web.dev/articles/prefers-color-scheme).
- *Proposal:* **UX-47** (spec below).

**R2-F4 The theme is hard to change.**
- *Where it is:* Appearance is a segmented control at the bottom of You, after the "How Cappy works" essay, and absent from the desktop header.
- *Owner:* "it needs to be easy to change to light mode".
- *Proposal:* **UX-48**.

**R2-F5 The full-screen gallery is covered by the page.**
- *Measured:* the viewer is a `fixed z-[70]` div, but the listing's sticky bar (z-30) and back button paint above it and hide "1 / 2" (inside a lower stacking context).
- *Accessibility:* `aria-modal` is set on a div whose background is not inert.
- *Proposal:* **UX-49**. Use `<dialog>.showModal()` (the top layer), a black backdrop in both themes, and the APG carousel roles (https://www.w3.org/WAI/ARIA/apg/patterns/carousel/).

**R2-F6 The confirm button contradicts the flow.**
- *EN:* "Book and pay · €16.00" under "Nothing is charged yet. Your card is held…", on a listing whose bar says "Request".
- *DE:* "Zahlungspflichtig buchen" for a request.
- *Styling:* the reassurance box is `warn` amber with an ⓘ, so a calming message reads as a warning. There's no payment-method row.
- *Why it matters:* Baymard ranks card-security distrust at 19 % and a total not shown upfront at 12 % among abandonment reasons (https://baymard.com/lists/cart-abandonment-rate). A button that says "pay" over a "nothing is charged" message is the kind of mismatch that erodes trust.
- *Proposal:* **UX-50**.

**R2-F7 After the request, the only sticky action is "Withdraw from this booking".**
- *What's missing:* no confirmation moment and no "Message Nadia". This contradicts UX-25's own rule (destructive actions in an overflow).
- *Proposal:* **UX-51**, and UX-40.

**R2-F8 A request creates no conversation.**
- *Seen:* host 2's fresh request is not in the Inbox. `InboxItem.lastMessage` is required, so a thread only exists after a message.
- *Why it matters:* on Airbnb the request *is* the first thread item. Here the buyer's first question has no home, and the owner sees the request only in Earn.
- *Proposal:* **UX-52**.

**R2-F9 The chosen day is invisible once applied.**
- *Seen:* choosing "Tomorrow" puts `on=2026-09-27` in the URL, but the chip still reads "2 hours · 47 mi".
- *Contradiction:* "Needed within 14 days" stays selectable next to a fixed day.
- *Proposal:* **UX-55** (with UX-18).

**R2-F10 200 % text breaks short headings.**
- *Seen:* `hyphens: auto` plus a last-resort break turns "Earn" into "Ear / n" (390, 375) and "Ea / rn" (360), with no hyphen.
- *Why it matters:* `hyphenate-limit-chars` sets the minimum word length and the letters before and after the break (https://developer.mozilla.org/en-US/docs/Web/CSS/hyphenate-limit-chars).
- *Proposal:* **UX-54**.

**R2-F11 Crimson used as data, amber as comfort.**
- *Seen:* the Earn and listing week charts fill "Sold" and "Your booking" in `--sold` = `--accent`, so the audit counts 4–6 accent fills on Earn. "Waiting for Nadia" and "Nothing is charged yet" are `warn` callouts.
- *Rule broken:* rulebook §3: one accent-filled control per view; crimson is never decoration.
- *Proposal:* **UX-61**.

**R2-F12 Screen-reader gaps on the key flows.**
- *Found:*
  - After each route change `document.activeElement` is `BODY`. `main#main` has `tabIndex=-1` but is never focused.
  - No polite live region exists before the first toast.
  - The notification unread dot is `aria-hidden`, with no text alternative.
  - The gallery strip has no `aria-roledescription`.
  - The toast rendered over the middle of the login form.
- *Why it matters:* Gatsby's user testing found focus on the new heading preferred (https://www.gatsbyjs.com/blog/2019-07-11-user-testing-accessible-client-routing/). A live region must exist before its content changes (https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions).
- *Proposal:* **UX-57**.

**R2-F13 Notifications speak like an email.**
- *Seen:* "…booked instantly by Demo Buyer. The details are in the app." shown inside the app. The title repeats the listing and time from the body. The notifications badge counts on "You" as well as on the bell.
- *Proposal:* **UX-62**.

**R2-F14 The desktop listing mosaic assumes 5 photos.**
- *Seen:* with 2 photos, the second tile is a quarter-size square and the rest of the row is empty. The category chip and the heart float over the page background.
- *Proposal:* **UX-56**.

**R2-F15 Localisation.**
- *Seen:*
  - The FR dock truncates "Réservat…" at every width.
  - Listing titles, descriptions and reviews stay English in DE/FR, with no "original language" label (UX-33).
  - The chart's day labels wrap to two lines at 360 ("Mo / 28").
- *Proposal:* **UX-66**, with UX-33.

**R2-F16 Rulebook conformance, measured** (rule → measured):
- *Side gutter:* rule 16 on the phone → **20** everywhere. The rule is probably what's wrong; see amendments.
- *Card padding:* rule 16 → **20** (Bookings, Earn, Listing, You).
- *Phone body text:* rule 17 → **13 and 15** (Listing: 14× 13 px, 8× 15 px; Earn: 9× 15 px).
- *Dock labels:* rule 11–12 → **10.5**.
- *Buttons:*
  - Secondary: rule 40 → **34** ("Add", "Open booking", "View as a guest", "Edit", "Pause", "Remove").
  - Primary: rule 48 → **52** (sticky "Request").
  - Compact 32 is used on the phone.
- *Tap targets:* rule ≥ 44 → under 44 per screen: Explore 29, Listing 25, You 26, Earn 14. Worst are the notification checkboxes (20×20), "Edit profile" (69×18), the rating link (56×22), the heart (36×36), back (40×40), chips (36) and the dock "+" (44×40).
- *4 px grid:* off-grid values on every screen: gaps 3, 5, 6, 10, 14; paddings 6, 10, 11, 14; margins 6, 10, 25.5.
- *One accent fill per view:* 2 on Bookings ("+" and "Open booking"), 2 on Listing (Request and the chart), 5 or more on Earn.
- *Hairlines:* rule ≥ 1.5:1 → **1.33** light and **1.35** dark.
- *Dock:* opaque or 85 % plus blur → **55 %** (dark) and see-through in light. Active pill → `--sunken`. Bottom padding "dock + 16" → content is visible under the bar on Earn at all four sizes.
- *Contrast:* the audit found **no text pair under 4.5:1** on solid surfaces in either theme at any width. The failures are non-text (surfaces, lines, pill) and text over glass.
- *Horizontal scroll:* none at 360–430.

## R2.4 Specs for the builder (P0)

### UX-46 Phone dock redesign

**Items.** Five: **Explore · Bookings · Inbox · Earn · You**. The crimson "+" leaves the bar. Creation moves to:
- a "List something" primary in the Earn header (already "+ Add"; make it the filled accent there);
- an empty-state action on Earn;
- the desktop header, as today.

This follows the HIG ("navigation, not actions"), M3 (3–5), Airbnb, Instagram 2025 and the rulebook.

**Geometry** (4 px grid):

| Part | Value |
|---|---|
| Bar | Full width, docked to the bottom edge (not a floating capsule): height 56 + `env(safe-area-inset-bottom)`, content box 56. Items centred in a max 480 px row. Radius 0, with a 1 px top hairline `line` (the amended 1.5:1 value) |
| Item | Equal flex, min 64 wide at 360 (5 × 64 = 320 plus 2 × 20 gutter). Hit area the whole cell (≥ 56 × 56) |
| Active indicator | A 56 × 32 capsule (`radius-full`) behind the icon, centred at y = 20 |
| Icon | 24 px on a 24 grid, 1.75 stroke; **filled variant when active** (HIG "prefer filled") |
| Label | 12 / 16 `text-caption` 12, weight 500, 600 when active. 4 below the indicator; never truncated. At 200 % text it goes icons-only with the names in `aria-label` (as today) |
| Badge | Min 16 × 16, `radius-full`, `text-caption` 11 bold tabular. Anchored at the indicator's top-right (x +4, y −4) *inside* the bar, with a 2 px ring in the bar colour. Numbers above 9 show "9+". Never clipped. Unread messages on **Inbox**, requests waiting on **Bookings** (host side) and **Earn** (payout action needed); **none on You**. The bell keeps its own count |

**Colours** (tokens):

| | Light | Dark |
|---|---|---|
| Bar | `elevated` #ffffff at 92 %, blur 20, saturate 180 %; opaque `elevated` under Reduce Transparency | `elevated` (new #232b24) at 94 %, blur 20; opaque under Reduce Transparency |
| Top hairline | `line` (α .20) | `line` (α .18) |
| Inactive icon + label | `ink-3` #5a6157 (≥ 6:1 on the bar) | `ink-3` (new #a8b0a4, 6.5:1 on #232b24) |
| Active indicator | `accent-subtle` #f9eaeb | `pill`, a new token #38443a (1.6:1 against the bar, clearly visible) |
| Active icon + label | `accent-text` #8b0d1a | `ink` #eef0ea |
| Badge | `badge` #8b0d1a / `on-badge` #fff (9.7:1) | `badge` #e0525f / `on-badge` #1a0507 (5.2:1) |

**Behaviour.**
- The indicator animates its width 0 → 56 and opacity in 150 ms `ease-standard` on a tab change (transform only: `scaleX`).
- **Hide on scroll** (iOS 26 minimise, simplified): after 48 px of downward scroll, translate the bar down by its content height (56), leaving the safe area painted, over 250 ms `ease-accelerate`. It returns on any upward scroll of 8 px or more, on reaching the top, or on focus inside it. Never on the first screen height. Off under reduced motion (stays visible).
- Every scroll view pads its bottom with `--dock-h + 16`.
- Detail routes keep hiding it (UX-13).
- The desktop header is unchanged, except the bell badge also moves off "You".

**Acceptance.**
- At 360, 375, 390 and 430 in light and dark: no label truncated (EN/DE/FR); no content legible through the bar; badge unclipped at 100 % and 200 %; the indicator ≥ 1.5:1 against the bar; inactive labels ≥ 4.5:1.
- `check:contrast` gains the pairs `ink-3/elevated`, `accent-text/accent-subtle`, `ink/pill` and `on-badge/badge`.

### UX-47 Dark mode fix

**Surfaces** (each step about +4.5 L\*, distinct from the one below):

| Token | Now | Proposed | L\* | Use |
|---|---|---|---|---|
| `page` | #0f1410 | **#121813** | 7.5 | Base |
| `sunken` | #0b0f0c (below the page) | **#161c17** | 9.5 | Fills and placeholders sit *above* the base, never a hole |
| `surface` | #171d18 | **#1a211b** | 11.9 | Cards |
| `elevated` | #1f2620 | **#232b24** | 16.6 | Sheets, dialogs, dock, popovers |
| `overlay` (new) | — | **#2c352d** | 21.1 | Menus over sheets, hovered rows |
| `pill` (new) | — | **#38443a** | 27.5 | Selected segments, the dock indicator, selected chips |
| `line` | α .12 (1.35:1) | **α .18** (1.67–1.71:1) | | |
| `line-strong` | α .28 | α .32 | | Input borders ≥ 3:1 stays |

**Text:**
- `ink` #eef0ea stays (15.7:1 on the new page).
- `ink-3` → **#a8b0a4** and `ink-4` → **#959d90**. These keep ≥ 4.5:1 up to `overlay` (4.54:1) and ≥ 5.2:1 on `elevated`.

**Accent:**
- Keep #e0525f with dark text (5.2:1).
- Reduce it to one fill per view (UX-61).
- **Disabled** = `pill` fill + `ink-4` text (UX-7), never 30 % crimson.

**Imagery:**
- Listing photos and the Welcome collage get `filter: brightness(.9)` in dark (the rulebook's 8–12 %); gallery full screen is excluded.
- The colour placeholder uses `photoMeta.color` at 70 % mixed into `sunken`.
- Plates keep `field` #1f3a24 but gain a 1 px `line` edge.
- Transparent PNG uploads sit on a `surface` tile.

**Display type:** in dark, Bodoni only at 34 px and up (`headline`, `display`). Screen titles and empty-state titles at 28 go to Archivo 600, or Bodoni at `wght` +100. The hairlines at 28 px on dark are what breaks "yet" into "yct".

**Materials:**
- Content sheets and the confirm sheet become opaque `elevated`; glass stays only on the dock and floating buttons (Apple: no glass in the content layer).
- Scrim `rgba(0,0,0,.6)`.
- The full-screen gallery is `#000` in both themes, with white controls on a 40 % black chip.

**States:**
- Reassurance ("Nothing is charged yet") uses a neutral `sunken` box with a lock icon, not `warn`.
- `warn` stays for real warnings only.

**Acceptance.**
- Every pair in `check:contrast` passes in both themes, plus surface-step pairs (each ≥ 1.15:1 against the level below) and `line` ≥ 1.5:1.
- The 390 before/after screenshots in both themes are attached to the PR.

### UX-48 One-tap theme switch

- **Phone:** a sun/moon icon button (44 × 44) in the You header, cycling System → Light → Dark. It shows a toast "Appearance: Light" with "Undo". The Appearance row moves into a Preferences group near the top of You (with Language and Notifications), not after the essay.
- **Desktop:** the same button left of the bell in the header, and a System · Light · Dark segmented switch in the footer next to the language switch.
- **Change:** a 150 ms crossfade via `startViewTransition`, none under reduced motion.
- **Default:** keep **System** (Apple advises against an app-only appearance), but make the override one tap from every main screen. See the rulebook amendment on "light is the default".

## R2.5 New proposals

**P0**
- [ ] UX-46 [web]+[app] Phone dock redesign per R2.4: 5 destinations, no "+" in the bar, full-width bar with the bottom safe area, 56×32 active indicator (`accent-subtle` light, `pill` dark) with a filled icon, 12 px labels in `ink-3`, 16 px ringed badges never clipped and never on "You", 92–94 % bar with blur (opaque under Reduce Transparency), hide on scroll, icons-only at 200 % — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/tab-bars.json · https://raw.githubusercontent.com/material-components/material-components-android/master/docs/components/BottomNavigation.md
- [ ] UX-47 [design]+[web] Dark-mode fix per R2.4: surface ladder `page` #121813 → `sunken` #161c17 → `surface` #1a211b → `elevated` #232b24 → `overlay` #2c352d → `pill` #38443a; `line` α .18; `ink-3` #a8b0a4, `ink-4` #959d90; photos `brightness(.9)`; Bodoni ≥ 34 px only in dark; opaque content sheets; black full-screen gallery; disabled = `pill` + `ink-4`; surface-step and line pairs in `check:contrast` — https://m2.material.io/design/color/dark-theme.html · https://web.dev/articles/prefers-color-scheme
- [ ] UX-48 [web] One-tap theme switch: sun/moon in the You header and the desktop header, System · Light · Dark in the footer, Appearance moved into a Preferences group at the top of You, a 150 ms crossfade, "Undo" on the toast — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/dark-mode.json
- [ ] UX-49 [web] Full-screen gallery on the top layer: `<dialog>.showModal()` so the sticky bar and back button can't paint over it; `#000` backdrop in both themes; the counter visible; APG carousel roles (`aria-roledescription="carousel"`/`"slide"`, labelled slides, prev/next buttons); the page behind inert — https://www.w3.org/WAI/ARIA/apg/patterns/carousel/ · https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- [ ] UX-50 [web] Confirm button says what happens: request = "Request · €16.00 held" (DE "Zahlungspflichtig anfragen · 16,00 €", FR "Demander · 16,00 € bloqués"); instant = "Book and pay · €16.00"; "Nothing is charged yet" as a neutral box with a lock, not `warn`; a payment-method row (saved card or "Card, next step"); the cancellation line once, not three times — https://baymard.com/lists/cart-abandonment-rate · https://baymard.com/blog/perceived-security-of-payment-form
- [ ] UX-51 [web] Booking page after a request: sticky primary "Message Nadia" (and after acceptance "Directions"), "Withdraw" moved to the ⋯ overflow with a confirm; a status header with a countdown ("Nadia usually replies in ~12 min · 23:41 left to answer") — https://www.nngroup.com/articles/error-message-guidelines/
- [ ] UX-52 [web]+[backend] A request opens a thread: the Inbox lists every live booking with a system first line ("You requested Sat 8:00–12:00") and the status chip; a dedicated `/inbox/:bookingId` thread with the booking card pinned and a composer that follows the keyboard; empty state with "Find something nearby" — https://www.nngroup.com/articles/push-notification/
- [ ] UX-53 [design]+[backend] Demo and seed photos that show the thing (3D printers, saws, vans, studios), licensed per category and never reused within a category; the grid-claim rule gives the photo to the *best-matching* listing, not the first — https://www.nngroup.com/articles/trustworthy-design/
- [ ] UX-54 [web] 200 % text and hyphenation: `hyphenate-limit-chars: 8 4 4` and `overflow-wrap: normal` on screen titles, so "Earn" never breaks; `hyphens: auto` on body text with the element's `lang`; a 200 % screenshot pass at 360 in DE and FR in each verification round — https://developer.mozilla.org/en-US/docs/Web/CSS/hyphenate-limit-chars

**P1**
- [ ] UX-55 [web] The chosen When shows in the applied chips ("Tomorrow · from 2 PM", removable); "Needed within" hides once a day is picked; When also on text search; the day row as a horizontal strip, not 15 wrapping chips (with UX-15, UX-18, UX-21) — https://baymard.com/blog/how-to-design-applied-filters
- [ ] UX-56 [web] Desktop gallery mosaic by count: 1 = full width 16:9; 2 = 50/50; 3 = 2/3 + two stacked; 4 = 1 + 3; 5+ = 1 + 4 with "Show all n photos"; the category chip and heart always over a photo — https://baymard.com/research/product-page
- [ ] UX-57 [web] Screen readers on key flows: on each route change focus the `<h1>` (`tabindex=-1`) and announce the title in a permanent `role=status` region; result counts ("6 bookable slots") announced there; the unread dot gets text ("Unread"); toasts at the bottom above the dock/bar, never over a form; a VoiceOver (iOS Safari) and TalkBack (Chrome) script for Explore → Request, Inbox and AddListing in each verification round — https://www.gatsbyjs.com/blog/2019-07-11-user-testing-accessible-client-routing/ · https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions · https://www.gov.uk/service-manual/technology/testing-with-assistive-technologies
- [ ] UX-58 [web] Perceived performance: prefetch the listing and its slots on card hover/focus and when a card enters the viewport on phones (`queryClient.prefetchQuery`, staleTime 60 s); `ensureQueryData` before `transition()`, so the hero never morphs into a skeleton; browser/hardware Back (popstate) runs the pop transition too — https://tanstack.com/query/latest/docs/framework/react/guides/prefetching · https://developer.chrome.com/docs/web-platform/view-transitions/same-document
- [ ] UX-59 [web] Motion choreography: transition types (`startViewTransition({types:['push']})` and `:active-view-transition-type()`) instead of `data-nav`; `view-transition-class: card` for list items; the title and price of the tapped card morph with the photo (shared elements named only on the tapped card); the M3 spring pairs as `linear()` tokens (spatial 0.9/700, effects 1/1600) — https://developer.chrome.com/docs/web-platform/view-transitions/same-document · https://developer.mozilla.org/en-US/docs/Web/CSS/view-transition-class
- [ ] UX-60 [web] Materials: glass only on the dock and floating buttons; sheets, dialogs and the sticky action bar opaque `elevated` with a hairline; scrim 40 % ink light / 60 % black dark — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/materials.json
- [ ] UX-61 [web] One accent fill per view: "Sold" and "Your booking" bars in `ink` with a pattern or `money`, not crimson; secondary buttons outlined; `warn` only for warnings ("Payout on hold" yes, "Waiting for Nadia" and "Nothing is charged yet" no) — https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
- [ ] UX-62 [web] Notifications as app copy: no "The details are in the app"; the title says what happened ("Demo Buyer booked Bandsaw, Sat 9 PM"); tapping opens the booking; an icon per type; Today / Earlier; the count on the bell only (not on "You") — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/notifications.json
- [ ] UX-63 [web] Reviews that build trust: a 5–1 star distribution, the average only from 3 reviews, per-aspect counts kept, the owner's public reply under a review, sort by recent, and "Translated from English · Show original" on review text; the verified badge says what and when ("ID checked · Mar 2026") — https://www.airbnb.com/help/article/1257 · https://www.airbnb.com/help/article/1237
- [ ] UX-64 [design]+[web] Rulebook conformance sweep: off-grid values (3/5/6/10/11/14/25.5) to the 4 px scale; secondary buttons 40 (not 34) on the phone; targets ≥ 44 (heart, back, chips, rating link, "Edit profile", notification checkboxes → switches in rows); phone body 17 for reading text; card padding per the amended rule; a `check:tokens` rule for off-grid spacing classes — `.claude/skills/cappy-ui/SKILL.md` §1, §2, §4
- [ ] UX-65 [app]+[backend] Push that earns its place: prime after the first request or message (not at launch); Android channels "Booking updates" (high), "Messages" (high), "Reminders" (default), "News" (low); a "Reply" action on message pushes; in-app preferences mirror the channels — https://developer.android.com/develop/ui/views/notifications/channels · https://developer.android.com/develop/ui/views/notifications/notification-permission
- [ ] UX-66 [web] Localisation layout: FR dock label that fits ("Résas", or "Locations" if counsel prefers); times as `Intl.DateTimeFormat.formatRange` everywhere ("Sat 12 Sep, 10:00–13:00"); chart day labels that never wrap at 360; an `en-XA` pseudo-locale (+40 %, accented, bracketed) in the dev build and screenshot runs; logical CSS properties (`margin-inline-*`) for later RTL — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/formatRange · https://learn.microsoft.com/en-us/globalization/methodology/pseudolocalization

**P2**
- [ ] UX-67 [web] Map search spec for UX-16: price pins on the top ~20 results and dot pins for the rest; MapLibre clustering (`clusterRadius` 50, `clusterMaxZoom` 14); centre on likely bookings, not the list order; a bottom sheet over the map on phones; district-level fuzzing until acceptance — https://arxiv.org/html/2407.00091 · https://maplibre.org/maplibre-gl-js/docs/examples/create-and-style-clusters/
- [ ] UX-68 [app] Haptics map for UX-11: `selectionChanged` on slot/day/chip scrubs, `impact(Light)` on the heart, `notification(Success)` on request sent / accepted / published, `notification(Error)` on a refused card; never `vibrate()`; no-op on the web; a setting to turn them off — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/playing-haptics.json · https://developer.android.com/develop/ui/views/haptics/haptics-principles
- [ ] UX-69 [web] Image placeholders for every source (the demo stock too): a stored colour per photo, `content-visibility: auto` with `contain-intrinsic-size` on long result lists — https://web.dev/articles/content-visibility · https://web.dev/articles/cls
- [ ] UX-70 [web]+[design] Host listing wizard detail for UX-19: a visible step list with the current step, photos first with a cover picker and per-photo captions, autosave with "Save and exit" on every step, a review summary before Publish — https://www.nngroup.com/articles/wizards/ · https://www.airbnb.com/resources/hosting-homes/a/how-to-take-great-listing-photos-12

## R2.6 Rulebook amendments proposed (`.claude/skills/cappy-ui/SKILL.md`)

1. **§1 gutter.**
   - Conflict: the rule says 16 on the phone, but every screen uses 20, and round 1 §3.1 set 20.
   - Proposal: 20 at ≥ 375 px and 16 below, so the code isn't changed for nothing.
2. **§3 "light is the default".**
   - Conflict: `theme.ts` defaults to System, and Apple advises against an app-only appearance.
   - Proposal: **System is the default, with a one-tap override** (UX-48). Otherwise the rule and the code fight.
3. **§3 hairlines ≥ 1.5:1.**
   - Conflict: today's tokens are 1.33 / 1.35.
   - Proposal: state the token values that meet it: `line` α .20 light and α .18 dark.
4. **§3 dark surfaces.**
   - Gap: "about 4–6 % more lightness each" is not checkable.
   - Proposal: state it as L\* steps of 4–5 and ≥ 1.15:1 between adjacent levels. List the ladder of UX-47, and say `sunken` is *above* the page in dark.
5. **§4 disabled buttons.**
   - Conflict: "40 % opacity" gives 1.46:1 for crimson on dark, and round 1 UX-7 asks for a fill.
   - Proposal: disabled = `sunken` (light) / `pill` (dark) fill with `ink-4` text.
6. **§4 dock active pill.**
   - Gap: `accent-subtle` is 1.17:1 on white, which is fine only because the icon also fills and the label turns `accent-text`. Say so.
   - Proposal: define the dark value (`pill` #38443a, ≥ 1.5:1 against the bar). State where badges go (Inbox, Bookings, Earn; never You) and that the bar docks to the edge with the safe area.
7. **§4 chips "radius full".**
   - Conflict: round 1 §3.2 kept capsules for floating chrome, and the code mixes the two.
   - Proposal: filter and category chips full; choice chips inside forms (slots, durations) `radius-s`.
8. **§4 buttons.**
   - Gap: the sticky bar's primary is 52 and the phone uses 34 for secondaries.
   - Proposal: primary 48 (52 allowed in sticky bars); secondary 40; 32 desktop only. Add a **sticky action bar** spec (height 72 + safe area, opaque `elevated`, one primary).
9. **Missing specs.**
   - Toasts: bottom, above the bar, never over a form.
   - Route-change focus: to the `<h1>`.
   - Notification rows: icon, 2-line clamp, unread text.
   - Full-screen media: black, on the top layer.
   - Bodoni in dark: ≥ 34 px.
   - The theme toggle placement.
10. **§7 safe area.**
    - Gap: an iframe cannot simulate `env()`.
    - Proposal: `max(env(safe-area-inset-bottom), var(--test-safe-bottom, 0px))` in the one place the bar reads it, so a review can set `--test-safe-bottom: 34px`, or else a device pass.

## R2.7 READINESS §14 as seen now (for its owner; READINESS.md is not edited here)

| # | Criterion | Met? | Evidence now | Still needed |
|---|---|---|---|---|
| 1 | Imagery truth | No | The gallery, plates and the no-reuse rule were walked. But the demo seed shows unrelated stock first on Explore | UX-53; UX-49 and UX-56 for the gallery defects |
| 2 | Type legibility | Nearly | Archivo figures verified in EN/DE/FR; `check:tokens` text size 0 | Dock labels 10.5 → 12 (UX-46); Bodoni in dark ≥ 34 (UX-47); 200 % mid-word breaks (UX-54) |
| 3 | Token system | Partly | Semantic CSS tokens in both themes; `check:tokens` and `check:contrast` in CI | UX-47 ladder; DTCG + Figma (UX-5, UX-43); off-grid sweep (UX-64) |
| 4 | Contrast and accessibility | No | No text under 4.5:1 on solid surfaces in the audit | axe (UX-35); targets (UX-34, UX-64); focus and live regions (UX-57); gallery semantics (UX-49); non-text surface pairs (UX-47) |
| 5 | Price clarity | Partly | `PriceSummary` walked on the listing and confirm sheet; fee named once there | UX-50 button copy; `PriceSummary` on the booking page; "Cappy fee" strings (UX-22) |
| 6 | Search completeness | No | A day and start hour in category filters | UX-15, UX-55, UX-18, UX-16/UX-67 |
| 7 | Navigation model | No | Inbox destination; the dock hides on detail screens | UX-46 dock; UX-52 threads; UX-14 staff shell |
| 8 | Motion and feedback | Partly | Drag, detents, exits, push/pop walked | Optimistic UI (UX-10), haptics (UX-11/UX-68), Back transitions (UX-58) |
| 9 | Perceived performance | Partly | Hero priority, intrinsic sizes and `srcset` verified | Prefetch (UX-58), placeholders for all images (UX-69), a lab run, field vitals (UX-45) |
| 10 | Native feel | No | — | Safe area on the dock (UX-46), plugins (UX-37), bounce and pull to refresh (UX-38), device pass |
| 11 | Consistency | No | One `Sheet` | One card (UX-17), states (UX-7), one accent fill (UX-61), materials (UX-60), design sign-off |
| 12 | Localisation layout | No | FR spacing enforced; DE sticky bar fits | FR dock truncation (UX-66), mid-word breaks (UX-54), "original language" labels (UX-33, UX-63) |

**None of the twelve is met yet.** Criterion 2 is closest: UX-46 plus UX-54 would close it.

## R2.8 What could not be reviewed

- **Real devices and the safe area.** No iOS or Android shell was run. The home-indicator overlap is inferred from code, and haptics, keyboard, predictive back and wallets were not seen.
- **Screen readers.** VoiceOver and TalkBack were not run. The findings come from the DOM (focus, roles, live regions, names). UX-57 asks for a scripted pass.
- **A populated Inbox thread.** Sending a message was outside the data allowance, so the thread and bubble UI was read from `Inbox.tsx` and `Conversation.tsx`.
- **The Stripe payment step.** The fake provider held the card without showing it. UX-24's look is judged from `PayStep.tsx`.
- **Booking states beyond "requested"** (confirmed, in progress, finished) for host 2.
- **Reduced motion and Increase Contrast** could not be toggled in the browser, and were checked in code only.
- **Sources.** Vinted, Turo, Revolut and Instagram pages, Airbnb's listing-flow and messaging help, Baymard's review display and NN/g's map article could not be fetched. The dock comparison for those apps is the lead's own observation, marked as such.
