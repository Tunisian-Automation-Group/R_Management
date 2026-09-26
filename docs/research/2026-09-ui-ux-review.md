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
